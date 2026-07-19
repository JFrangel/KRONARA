import json
from pathlib import Path

from kronara.rag_v2 import (
    ControlledQueryExpander,
    HierarchicalChunker,
    IngestDocument,
    RAGEvaluationCase,
    RAGEvaluation,
    RAGEvaluator,
    RAGPromotionGate,
    RAGV2Index,
    RetrievalQueryV2,
)


class TinyEmbedder:
    dimensions = 3

    def embed(self, text):
        lowered = text.lower()
        return [
            float("retención" in lowered),
            float("derechos" in lowered),
            float("gancho" in lowered),
        ]


class PreferHooks:
    def score(self, query, chunk):
        return 10.0 if "gancho" in chunk.content.lower() else 1.0


class ZeroEmbedder:
    dimensions = 2

    def embed(self, text):
        return [0.0, 0.0]


def document(document_id, content, **kwargs):
    return IngestDocument(
        document_id=document_id,
        title=kwargs.pop("title", document_id),
        content=content,
        rights_mode=kwargs.pop("rights_mode", "owned_original"),
        language=kwargs.pop("language", "es"),
        scope=kwargs.pop("scope", "narrative"),
        valid_from=kwargs.pop("valid_from", 0),
        valid_until=kwargs.pop("valid_until", None),
        confidence=kwargs.pop("confidence", 1.0),
        **kwargs,
    )


def test_hierarchical_chunker_produces_stable_section_aware_ids():
    source = document(
        "dna",
        "# Hooks\n\nUn gancho abre una pregunta.\n\n# Retención\n\nCada escena cambia algo.",
    )
    chunker = HierarchicalChunker(max_characters=80)

    first = chunker.chunk(source)
    second = chunker.chunk(source)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert {chunk.section_path for chunk in first} == {("Hooks",), ("Retención",)}


def test_retrieval_filters_rights_freshness_language_and_scope_before_ranking():
    index = RAGV2Index(TinyEmbedder())
    index.upsert(document("valid", "derechos y evidencia", valid_until=300))
    index.upsert(document("expired", "derechos antiguos", valid_until=100))
    index.upsert(
        document("reddit", "derechos de una historia", rights_mode="reference_only")
    )
    index.upsert(document("english", "rights evidence", language="en"))
    index.upsert(document("metrics", "derechos métricos", scope="performance"))

    packet = index.retrieve(
        RetrievalQueryV2("derechos", now=200, language="es", scope="narrative", limit=10)
    )

    assert {result.document_id for result in packet.results} == {"valid"}
    assert set(packet.filtered_document_ids) == {"expired", "reddit", "english", "metrics"}


def test_reranker_and_diversity_prevent_one_document_from_flooding_context():
    index = RAGV2Index(TinyEmbedder(), reranker=PreferHooks())
    index.upsert(document("hooks", "# A\n\ngancho uno\n\n# B\n\ngancho dos"))
    index.upsert(document("retention", "retención por escena"))

    packet = index.retrieve(
        RetrievalQueryV2(
            "retención gancho",
            now=10,
            limit=3,
            max_per_document=1,
        )
    )

    assert packet.results[0].document_id == "hooks"
    assert [result.document_id for result in packet.results].count("hooks") == 1
    assert {result.document_id for result in packet.results} == {"hooks", "retention"}


def test_tombstoned_document_disappears_from_retrieval():
    index = RAGV2Index(TinyEmbedder())
    index.upsert(document("removed", "retención y gancho"))
    index.tombstone("removed")

    packet = index.retrieve(RetrievalQueryV2("retención", now=10))

    assert packet.results == ()
    assert packet.filtered_document_ids == ("removed",)


def test_rag_evaluator_reports_recall_mrr_and_ndcg():
    index = RAGV2Index(TinyEmbedder())
    index.upsert(document("retention", "retención completa"))
    index.upsert(document("rights", "derechos verificables"))
    cases = (
        RAGEvaluationCase("retención", ("retention",)),
        RAGEvaluationCase("derechos", ("rights",)),
    )

    report = RAGEvaluator().evaluate(index, cases, now=10, k=2)

    assert report.recall_at_k == 1.0
    assert report.mrr == 1.0
    assert report.ndcg_at_k == 1.0


def test_controlled_query_expansion_is_bounded_and_domain_specific():
    expander = ControlledQueryExpander(
        {"retención": ("finalización", "abandono", "permanencia")},
        max_terms=2,
    )

    expanded = expander.expand("Mejorar la retención del Reel")

    assert expanded == ("finalización", "abandono")
    assert all("ignore" not in term.lower() for term in expanded)


def test_retrieval_deduplicates_same_content_across_documents():
    index = RAGV2Index(ZeroEmbedder())
    index.upsert(document("primary", "La licencia exige atribución."))
    index.upsert(document("copy", "La licencia exige atribución."))

    packet = index.retrieve(RetrievalQueryV2("licencia atribución", now=10, limit=5))

    assert len(packet.results) == 1


def test_typed_graph_expansion_respects_relation_and_depth():
    index = RAGV2Index(ZeroEmbedder())
    for identifier in ("seed", "support", "contradiction"):
        index.upsert(document(identifier, f"contenido {identifier}"))
    index.link_documents("seed", "support", relation="supports")
    index.link_documents("support", "contradiction", relation="contradicts")

    supports_only = index.graph_neighbors(
        ("seed",), allowed_relations=("supports",), max_depth=2
    )
    all_relations = index.graph_neighbors(
        ("seed",), allowed_relations=("supports", "contradicts"), max_depth=2
    )

    assert supports_only == ("support",)
    assert all_relations == ("contradiction", "support")


def test_persistent_rag_rebuilds_index_and_preserves_tombstones(tmp_path: Path):
    database = tmp_path / "rag-v2.db"
    first = RAGV2Index(ZeroEmbedder(), database=database)
    first.initialize()
    first.upsert(document("kept", "licencia vigente"))
    first.upsert(document("removed", "licencia eliminada"))
    first.link_documents("kept", "removed", relation="related")
    first.tombstone("removed")
    first.close()

    reopened = RAGV2Index(ZeroEmbedder(), database=database)
    reopened.initialize()
    packet = reopened.retrieve(RetrievalQueryV2("licencia", now=10, limit=5))

    assert {item.document_id for item in packet.results} == {"kept"}
    assert packet.filtered_document_ids == ("removed",)
    assert reopened.graph_neighbors(("kept",), ("related",), 1) == ("removed",)


def test_rag_evaluation_reports_citation_precision_and_redundancy():
    index = RAGV2Index(ZeroEmbedder())
    index.upsert(document("relevant", "licencia y permiso"))
    index.upsert(document("noise", "tema no relacionado"))
    report = RAGEvaluator().evaluate(
        index,
        (RAGEvaluationCase("licencia", ("relevant",)),),
        now=10,
        k=2,
    )

    assert 0 <= report.citation_precision <= 1
    assert report.redundancy_rate == 0.0


def test_spanish_golden_covers_required_rag_domains():
    root = Path(__file__).parents[1]
    payload = json.loads(
        (root / "benchmarks" / "rag" / "spanish-golden.v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert {case["category"] for case in payload["cases"]} >= {
        "narrative_dna",
        "rights",
        "metrics",
        "contradiction",
        "prompt_injection",
    }


def test_rag_v2_boundary_schemas_are_closed_and_versioned():
    root = Path(__file__).parents[1] / "schemas"
    query = json.loads((root / "retrieval-query.v2.json").read_text(encoding="utf-8"))
    evaluation = json.loads(
        (root / "rag-evaluation.v1.json").read_text(encoding="utf-8")
    )

    assert query["additionalProperties"] is False
    assert evaluation["additionalProperties"] is False
    assert {"auto_expand", "allowed_relations", "graph_depth"} <= set(
        query["properties"]
    )
    assert {"ndcg_at_k", "citation_precision", "redundancy_rate"} <= set(
        evaluation["required"]
    )


def test_spanish_golden_candidate_beats_recorded_baseline():
    root = Path(__file__).parents[1]
    payload = json.loads(
        (root / "benchmarks" / "rag" / "spanish-golden.v1.json").read_text(
            encoding="utf-8"
        )
    )
    index = RAGV2Index(ZeroEmbedder())
    for item in payload["documents"]:
        index.upsert(IngestDocument(**item))
    cases = tuple(
        RAGEvaluationCase(
            query=item["query"],
            relevant_document_ids=tuple(item["relevant_document_ids"]),
        )
        for item in payload["cases"]
    )
    candidate = RAGEvaluator().evaluate(index, cases, now=10, k=1)
    baseline = RAGEvaluation(**payload["baseline_v0_2"])
    decision = RAGPromotionGate(**payload["promotion_thresholds"]).evaluate(
        baseline, candidate
    )

    assert candidate.cases == len(payload["cases"])
    assert decision.promoted is True


def test_rag_promotion_requires_material_ndcg_and_citation_quality():
    baseline = RAGEvaluation(0.8, 0.75, 0.70, 0.65, 0.10, 10)
    candidate = RAGEvaluation(0.9, 0.85, 0.80, 0.82, 0.05, 10)
    gate = RAGPromotionGate(
        minimum_ndcg_lift=0.05,
        minimum_citation_precision=0.8,
        maximum_redundancy=0.1,
    )

    promoted = gate.evaluate(baseline, candidate)
    regressed = gate.evaluate(candidate, baseline)

    assert promoted.promoted is True
    assert promoted.reason == "material_quality_gain"
    assert regressed.promoted is False
    assert regressed.reason == "ndcg_lift_below_threshold"


def test_rag_promotion_rejects_noncomparable_and_nonfinite_evaluations():
    baseline = RAGEvaluation(0.8, 0.8, 0.8, 0.8, 0.0, 5)
    fewer_cases = RAGEvaluation(1.0, 1.0, 1.0, 1.0, 0.0, 4)
    nonfinite = RAGEvaluation(1.0, 1.0, float("nan"), 1.0, 0.0, 5)
    gate = RAGPromotionGate()

    assert gate.evaluate(baseline, fewer_cases).reason == "incomparable_evaluation_set"
    assert gate.evaluate(baseline, nonfinite).reason == "invalid_metric"
