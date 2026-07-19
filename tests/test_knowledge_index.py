from pathlib import Path

from kronara.knowledge import KnowledgeDocument, LocalHybridIndex


class TinyEmbedder:
    dimensions = 3

    def embed(self, text):
        lowered = text.lower()
        return [
            float("paranormal" in lowered),
            float("familia" in lowered),
            float("justicia" in lowered),
        ]


def test_hybrid_index_combines_lexical_vector_and_graph_results(tmp_path: Path):
    index = LocalHybridIndex(tmp_path / "knowledge.db", TinyEmbedder())
    index.initialize()
    index.upsert(KnowledgeDocument("d1", "paranormal", "Puerta paranormal en hotel", "owned", 1.0))
    index.upsert(KnowledgeDocument("d2", "familia", "Conflicto de familia", "owned", 1.0))
    index.upsert(KnowledgeDocument("d3", "justicia", "Evidencia y justicia", "owned", 1.0))
    index.link("d1", "d2", "shared_emotion")

    results = index.search("historia paranormal de familia", limit=3)

    assert results[0].document_id in {"d1", "d2"}
    assert {item.document_id for item in results[:2]} == {"d1", "d2"}
    assert all(item.citation_uri.startswith("kronara://knowledge/") for item in results)


def test_hybrid_index_excludes_reference_only_story_text(tmp_path: Path):
    index = LocalHybridIndex(tmp_path / "knowledge.db", TinyEmbedder())
    index.initialize()

    index.upsert(KnowledgeDocument("r1", "source", "third party story body", "reference_only", 0.8))

    assert index.search("third party story body") == []

