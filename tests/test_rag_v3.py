from pathlib import Path
import json

import pytest

from kronara.embedding_registry import EmbeddingModelDescriptor
from kronara.rag_v2 import DeterministicHashEmbedder, IngestDocument
from kronara.rag_v3 import (
    EmbeddingCompatibilityError,
    RAGV3Index,
    RAGV3Evaluator,
    RetrievalEvaluationCaseV2,
    RetrievalQueryV3,
)


def descriptor(dimensions: int = 64) -> EmbeddingModelDescriptor:
    return EmbeddingModelDescriptor(
        alias="deterministic_dev",
        provider="local",
        model_id="kronara/deterministic-hash",
        kind="embedding",
        dimensions=dimensions,
        max_tokens=2048,
        languages=("es", "en"),
        normalized=False,
        query_instruction="",
        license="internal-test",
        version_hash=f"deterministic-v1-{dimensions}",
        privacy="local",
        health="development_only",
    )


def document(document_id: str, content: str, *, rights: str = "owned_original"):
    return IngestDocument(
        document_id=document_id,
        title=document_id,
        content=content,
        rights_mode=rights,
        language="es",
        scope="narrative",
        valid_from=100,
        valid_until=None,
        confidence=1.0,
        version=1,
    )


def query(text: str = "gancho retención") -> RetrievalQueryV3:
    return RetrievalQueryV3(
        text=text,
        now=200,
        language="es",
        scope="narrative",
        allowed_rights=("owned_original",),
        allowed_relations=("supports", "same_topic"),
        graph_depth=1,
        limit=4,
        max_per_document=2,
    )


def test_index_rejects_mixed_embedding_dimensions(tmp_path):
    index = RAGV3Index(
        tmp_path / "rag.db", descriptor(), DeterministicHashEmbedder(64)
    )

    with pytest.raises(EmbeddingCompatibilityError, match="dimensions"):
        index.upsert(document("doc_1", "Gancho narrativo"), vectors=[[0.0] * 32])
    index.close()


def test_v3_applies_rights_before_fts_vector_graph_and_rerank(tmp_path):
    index = RAGV3Index(
        tmp_path / "rag.db", descriptor(), DeterministicHashEmbedder(64)
    )
    index.upsert(document("owned", "# Hook\nUn gancho claro mejora la retención inicial."))
    index.upsert(
        document(
            "external",
            "# Hook\nUna historia externa con gancho y retención.",
            rights="reference_only",
        )
    )
    index.link_documents("owned", "external", "same_topic")

    packet = index.retrieve(query())

    assert packet.results
    assert {item.document_id for item in packet.results} == {"owned"}
    assert all(item.rights_mode == "owned_original" for item in packet.results)
    assert set(packet.stage_counts) == {
        "eligible",
        "lexical",
        "vector",
        "graph",
        "fused",
        "reranked",
        "deduplicated",
        "selected",
    }
    assert all(
        item.citation_uri.startswith("kronara://knowledge/")
        for item in packet.results
    )
    assert index.connection.execute(
        "SELECT count(*) FROM knowledge_chunks_fts"
    ).fetchone()[0] >= 2
    index.close()


class BrokenEmbedder:
    dimensions = 64

    def embed(self, _):
        raise RuntimeError("model unavailable")


def test_unavailable_vector_provider_falls_back_to_fts_with_warning(tmp_path):
    index = RAGV3Index(tmp_path / "rag.db", descriptor(), BrokenEmbedder())
    chunks = index.chunker.chunk(document("owned", "Gancho y retención para un Reel."))
    index.upsert(
        document("owned", "Gancho y retención para un Reel."),
        vectors=[[0.1] * 64 for _ in chunks],
    )

    packet = index.retrieve(query())

    assert packet.results
    assert packet.degradations == ("vector_unavailable",)
    index.close()


def test_tombstone_removes_document_from_all_retrieval_stages(tmp_path):
    index = RAGV3Index(
        tmp_path / "rag.db", descriptor(), DeterministicHashEmbedder(64)
    )
    index.upsert(document("owned", "Gancho y retención para un Reel."))
    assert index.retrieve(query()).results

    index.tombstone("owned")

    assert index.retrieve(query()).results == ()
    index.close()


def test_spanish_golden_v2_evaluates_persistent_pipeline(tmp_path):
    payload = json.loads(
        Path("benchmarks/rag/spanish-golden.v2.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 2
    assert len(payload["cases"]) >= 10
    assert {
        "narrative",
        "rights",
        "performance",
        "contradictions",
        "operations",
        "injection",
    } <= {item["domain"] for item in payload["cases"]}
    index = RAGV3Index(
        tmp_path / "golden.db", descriptor(), DeterministicHashEmbedder(64)
    )
    for item in payload["documents"]:
        index.upsert(
            document(
                item["document_id"],
                item["content"],
                rights=item["rights_mode"],
            )
        )
    cases = tuple(
        RetrievalEvaluationCaseV2(
            query=item["query"],
            relevant_document_ids=tuple(item["relevant_document_ids"]),
            domain=item["domain"],
        )
        for item in payload["cases"]
    )

    evaluation = RAGV3Evaluator().evaluate(index, cases, now=200, k=4)

    assert evaluation.cases == len(cases)
    assert evaluation.recall_at_k >= 0.9
    assert evaluation.ndcg_at_k >= 0.75
    assert evaluation.citation_precision >= 0.25
    index.close()
