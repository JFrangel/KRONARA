from pathlib import Path

from kronara.embedding_registry import (
    EmbeddingRegistry,
    ProductionEmbeddingFactory,
)
from kronara.rag_v2 import DeterministicHashEmbedder


ROOT = Path(__file__).resolve().parents[1]


class FakeVector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeSentenceTransformer:
    def encode(self, texts, normalize_embeddings, show_progress_bar):
        assert texts
        assert normalize_embeddings
        assert not show_progress_bar
        return [FakeVector([0.01] * 1024)]


class FakeCrossEncoder:
    def predict(self, pairs):
        return [0.9 for _ in pairs]


def registry():
    return EmbeddingRegistry.load(ROOT / "config" / "models" / "embeddings.v1.json")


def test_factory_activates_real_multilingual_embedding_and_reranker_when_local():
    runtime = ProductionEmbeddingFactory(
        registry(),
        embedding_loader=lambda _: FakeSentenceTransformer(),
        reranker_loader=lambda _: FakeCrossEncoder(),
    ).build("bge_m3", reranker_alias="bge_reranker_v2_m3")

    assert runtime.descriptor.alias == "bge_m3"
    assert runtime.embedder.dimensions == 1024
    assert runtime.reranker is not None
    assert runtime.degradations == ()
    assert len(runtime.embedder.embed("historia original en español")) == 1024


def test_factory_falls_back_explicitly_without_downloading_model_weights():
    def unavailable(_):
        raise OSError("weights are not installed")

    runtime = ProductionEmbeddingFactory(
        registry(), embedding_loader=unavailable
    ).build("bge_m3", reranker_alias="bge_reranker_v2_m3")

    assert runtime.descriptor.alias == "deterministic_dev"
    assert isinstance(runtime.embedder, DeterministicHashEmbedder)
    assert runtime.reranker is None
    assert runtime.degradations == ("production_embedding_unavailable",)


def test_factory_degrades_before_serving_queries_when_reranker_weights_are_missing():
    def unavailable_reranker(_):
        raise OSError("reranker weights are not installed")

    runtime = ProductionEmbeddingFactory(
        registry(),
        embedding_loader=lambda _: FakeSentenceTransformer(),
        reranker_loader=unavailable_reranker,
    ).build("bge_m3", reranker_alias="bge_reranker_v2_m3")

    assert runtime.descriptor.alias == "deterministic_dev"
    assert runtime.reranker is None
    assert runtime.degradations == ("production_embedding_unavailable",)
