from kronara.rag_v2 import (
    HierarchicalChunker,
    IngestDocument,
    RAGEvaluationCase,
    RAGEvaluator,
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
