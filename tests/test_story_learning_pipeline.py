from kronara.embedding_registry import EmbeddingModelDescriptor
from kronara.rag_v2 import DeterministicHashEmbedder
from kronara.rag_v3 import RAGV3Index, RetrievalQueryV3
from kronara.store import KronaraStore
from kronara.story_reuse import (
    OwnedStoryPerformance,
    StoryExampleRepository,
    StoryQualityEvidence,
    StoryReuseGate,
)
from kronara.training_rights import RightsMode, TrainingAsset


def descriptor():
    return EmbeddingModelDescriptor(
        alias="deterministic_dev",
        provider="kronara",
        model_id="kronara/deterministic-hash",
        kind="embedding",
        dimensions=64,
        max_tokens=2048,
        languages=("es", "en"),
        normalized=False,
        query_instruction="",
        license="internal-test-only",
        version_hash="deterministic-hash-v1",
        privacy="local",
        health="development_only",
    )


def performance(story_id):
    return OwnedStoryPerformance(
        story_id=story_id,
        platform="facebook",
        format="reel",
        sample_size=300,
        metric_window_hours=72,
        relative_lift=0.12,
        confidence_low=0.04,
        confidence_high=0.20,
        comparable_cohort=True,
        outlier_share=0.1,
        reputational_risk="low",
        evidence_refs=("metric:facebook:1",),
    )


def quality():
    return StoryQualityEvidence(
        narrative_passed=True,
        originality_passed=True,
        safety_passed=True,
        publication_succeeded=True,
        golden_no_regression=True,
        evidence_refs=("qc:story:1",),
    )


def query(text):
    return RetrievalQueryV3(
        text=text,
        now=1_900_000_000,
        language="es",
        scope="narrative",
        allowed_rights=("promoted_learning",),
    )


def test_owned_story_is_promoted_into_active_rag_and_reversibly_tombstoned(tmp_path):
    story_id = "owned_story_success_1"
    index = RAGV3Index(
        tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64)
    )
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    repository = StoryExampleRepository(store=store, index=index)
    decision = StoryReuseGate().evaluate(
        performance(story_id),
        quality(),
        TrainingAsset(
            asset_id=story_id,
            rights_mode=RightsMode.OWNED_ORIGINAL,
            source_uri=f"kronara://artifacts/{story_id}",
        ),
    )

    promoted = repository.promote(
        decision,
        content="Una restauradora descubre una respiración imposible dentro de un audio propio.",
    )

    packet = index.retrieve(query("restauradora respiración audio"))
    assert promoted.status == "promoted_rag_example"
    assert {item.document_id for item in packet.results} == {story_id}
    assert {item.rights_mode for item in packet.results} == {"promoted_learning"}
    assert index.promotion_evidence(story_id) == (
        "metric:facebook:1",
        "qc:story:1",
        f"kronara://artifacts/{story_id}",
    )

    repository.revert(story_id, "metric regression")

    assert index.retrieve(query("restauradora respiración audio")).results == ()
    store.close()
    index.close()


def test_external_reddit_story_cannot_be_promoted_to_active_rag(tmp_path):
    story_id = "external_story_1"
    index = RAGV3Index(
        tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64)
    )
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    repository = StoryExampleRepository(store=store, index=index)
    decision = StoryReuseGate().evaluate(
        performance(story_id),
        quality(),
        TrainingAsset(
            asset_id=story_id,
            rights_mode=RightsMode.REFERENCE_ONLY,
            source_uri="https://reddit.com/r/stories/external_story_1",
        ),
    )

    assert decision.status == "rejected"
    try:
        repository.promote(decision, content="Texto externo")
    except ValueError as error:
        assert "approved RAG candidate" in str(error)
    else:
        raise AssertionError("external content was unexpectedly promoted")
    assert index.retrieve(query("Texto externo")).results == ()
    store.close()
    index.close()
