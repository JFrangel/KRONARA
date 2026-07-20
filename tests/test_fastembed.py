import math

import pytest

from kronara.embedding_registry import MULTILINGUAL_MINILM_384, FastEmbedProvider


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def test_fastembed_descriptor_shape():
    assert MULTILINGUAL_MINILM_384.dimensions == 384
    assert MULTILINGUAL_MINILM_384.kind == "embedding"
    provider = FastEmbedProvider(MULTILINGUAL_MINILM_384)
    assert provider.dimensions == 384
    assert provider.embed("   ") == [0.0] * 384  # empty text -> zero vector, no load


def test_fastembed_produces_real_semantic_embeddings():
    """Downloads the ONNX model (cached) and proves real semantics.

    Skips cleanly when fastembed or the one-time model download is unavailable.
    """
    pytest.importorskip("fastembed")
    provider = FastEmbedProvider(MULTILINGUAL_MINILM_384)
    try:
        a = provider.embed("Una familia esconde un secreto sobre una herencia.")
        b = provider.embed("El secreto de la herencia divide a la familia.")
        c = provider.embed("La receta lleva harina, huevos y azúcar.")
    except Exception as error:  # network/model unavailable
        pytest.skip(f"fastembed model unavailable: {error}")

    assert len(a) == 384
    related = _cosine(a, b)
    unrelated = _cosine(a, c)
    # A real semantic model ranks the related pair above the unrelated one;
    # the deterministic hash fallback could not do this.
    assert related > unrelated
    assert related > 0.5
