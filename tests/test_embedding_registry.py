from pathlib import Path

from kronara.embedding_registry import (
    CrossEncoderReranker,
    EmbeddingEvaluation,
    EmbeddingModelDescriptor,
    EmbeddingRegistry,
    SentenceTransformerEmbeddingProvider,
)
from kronara.rag_v2 import KnowledgeChunk


CONFIG = Path("config/models/embeddings.v1.json")


def evaluation(alias: str, *, ndcg: float, cases: int = 20) -> EmbeddingEvaluation:
    return EmbeddingEvaluation(
        evaluation_id=f"eval_{alias}",
        model_alias=alias,
        golden_set_hash="golden-v2-hash",
        recall_at_k=0.9,
        mrr=0.85,
        ndcg_at_k=ndcg,
        citation_precision=0.8,
        redundancy_rate=0.1,
        latency_ms=40.0,
        memory_mb=600.0,
        cases=cases,
    )


def test_registry_loads_real_multilingual_candidates_and_dev_fallback():
    registry = EmbeddingRegistry.load(CONFIG)

    assert registry.get("bge_m3").model_id == "BAAI/bge-m3"
    assert registry.get("bge_m3").dimensions == 1024
    assert registry.get("multilingual_e5_large").query_instruction
    assert registry.get("bge_reranker_v2_m3").kind == "reranker"
    assert registry.get("deterministic_dev").health == "development_only"


def test_activation_requires_comparable_material_quality_gain():
    registry = EmbeddingRegistry.load(CONFIG)
    baseline = evaluation("deterministic_dev", ndcg=0.60)
    promoted = registry.activate("bge_m3", evaluation("bge_m3", ndcg=0.67), baseline)
    weak = registry.activate("multilingual_e5_large", evaluation("multilingual_e5_large", ndcg=0.61), baseline)

    assert promoted.promoted
    assert promoted.index_id.startswith("embidx_bge_m3_")
    assert weak.promoted is False
    assert weak.reason == "ndcg_lift_below_threshold"


def test_development_fallback_cannot_be_promoted_to_production():
    registry = EmbeddingRegistry.load(CONFIG)
    descriptor = registry.get("deterministic_dev")

    decision = registry.activate(
        descriptor.alias,
        evaluation(descriptor.alias, ndcg=0.99),
        evaluation("baseline", ndcg=0.50),
    )

    assert not decision.promoted
    assert decision.reason == "development_only_model"


def test_descriptor_rejects_invalid_dimension_and_version_hash():
    try:
        EmbeddingModelDescriptor(
            alias="bad",
            provider="local",
            model_id="bad",
            kind="embedding",
            dimensions=0,
            max_tokens=10,
            languages=("es",),
            normalized=True,
            query_instruction="query: ",
            license="MIT",
            version_hash="short",
            privacy="local",
            health="healthy",
        )
    except ValueError as error:
        assert "dimensions" in str(error) or "version" in str(error)
    else:
        raise AssertionError("invalid descriptor must fail")


class FakeEmbeddingModel:
    def __init__(self, dimensions):
        self.dimensions = dimensions
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        return [[0.25] * self.dimensions]


def test_sentence_transformer_adapter_uses_descriptor_and_validates_dimensions():
    descriptor = EmbeddingRegistry.load(CONFIG).get("bge_m3")
    model = FakeEmbeddingModel(descriptor.dimensions)
    provider = SentenceTransformerEmbeddingProvider(
        descriptor,
        model_loader=lambda _: model,
    )

    vector = provider.embed("gancho narrativo")

    assert len(vector) == descriptor.dimensions
    assert model.calls[0][1]["normalize_embeddings"] is True


class FakeCrossEncoder:
    def predict(self, pairs):
        assert pairs == [("retención", "un gancho claro")]
        return [0.87]


def test_multilingual_cross_encoder_adapter_scores_query_and_chunk():
    descriptor = EmbeddingRegistry.load(CONFIG).get("bge_reranker_v2_m3")
    reranker = CrossEncoderReranker(
        descriptor,
        model_loader=lambda _: FakeCrossEncoder(),
    )
    chunk = KnowledgeChunk(
        chunk_id="chunk_1",
        document_id="doc_1",
        section_path=("Hook",),
        content="un gancho claro",
        rights_mode="owned_original",
        language="es",
        scope="narrative",
        valid_from=1,
        valid_until=None,
        confidence=1.0,
        version=1,
    )

    assert reranker.score("retención", chunk) == 0.87
