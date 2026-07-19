from datetime import UTC, datetime, timedelta

from kronara.embedding_registry import EmbeddingModelDescriptor
from kronara.performance import MetricSnapshot
from kronara.performance_learning import PerformanceLearningService
from kronara.rag_v2 import DeterministicHashEmbedder
from kronara.rag_v3 import RAGV3Index, RetrievalQueryV3
from kronara.store import KronaraStore
from kronara.story_reuse import StoryExampleRepository, StoryQualityEvidence
from kronara.training_rights import RightsMode, TrainingAsset


NOW = datetime(2026, 7, 19, 18, tzinfo=UTC)


def descriptor():
    return EmbeddingModelDescriptor(
        alias="deterministic_dev",
        provider="kronara",
        model_id="kronara/deterministic-hash",
        kind="embedding",
        dimensions=64,
        max_tokens=2048,
        languages=("es",),
        normalized=False,
        query_instruction="",
        license="internal-test-only",
        version_hash="deterministic-hash-v1",
        privacy="local",
        health="development_only",
    )


def snapshot(content_id, completions, *, voice="voice-a", hook="hook-a"):
    return MetricSnapshot(
        schema_version=1,
        snapshot_id=f"metric-{content_id}",
        content_id=content_id,
        platform="facebook",
        published_at=NOW - timedelta(hours=72),
        observed_at=NOW,
        metric_window_hours=72,
        impressions=400,
        starts=300,
        completions=completions,
        replays=30,
        shares=20,
        watch_time_seconds=18_000,
        duration_seconds=90,
        voice_id=voice,
        topic="misterio familiar",
        hook_id=hook,
        publication_hour=18,
        audience_segment="latam-general",
    )


def quality():
    return StoryQualityEvidence(
        narrative_passed=True,
        originality_passed=True,
        safety_passed=True,
        publication_succeeded=True,
        golden_no_regression=True,
        evidence_refs=("qc:owned-winning-story",),
    )


def test_supported_owned_story_metrics_promote_reversible_rag_learning(tmp_path):
    story_id = "owned-winning-story"
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    index = RAGV3Index(
        tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64)
    )
    service = PerformanceLearningService(
        repository=StoryExampleRepository(store=store, index=index)
    )

    result = service.learn(
        target_story_id=story_id,
        snapshots=(
            snapshot(story_id, 250, voice="voice-winner", hook="hook-winner"),
            snapshot(
                "owned-winning-story-variant",
                240,
                voice="voice-winner",
                hook="hook-winner",
            ),
            snapshot("baseline-1", 150),
            snapshot("baseline-2", 145),
        ),
        quality=quality(),
        asset=TrainingAsset(
            asset_id=story_id,
            rights_mode=RightsMode.OWNED_ORIGINAL,
            source_uri=f"kronara://artifacts/{story_id}",
        ),
        content="Historia propia sobre una restauradora y una respiración imposible.",
    )

    assert result.diagnosis.status == "ready_for_experiment"
    assert not any(item.causal_claim for item in result.diagnosis.hypotheses)
    assert result.decision.status == "promoted_rag_example"
    assert result.performance.comparable_cohort
    assert result.performance.confidence_low > 0
    packet = index.retrieve(
        RetrievalQueryV3(
            "restauradora respiración",
            now=1_900_000_000,
            language="es",
            scope="narrative",
            allowed_rights=("promoted_learning",),
        )
    )
    assert {item.document_id for item in packet.results} == {story_id}
    store.close()
    index.close()


def test_insufficient_or_external_metrics_never_promote_learning(tmp_path):
    story_id = "external-story"
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    index = RAGV3Index(
        tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64)
    )
    service = PerformanceLearningService(
        repository=StoryExampleRepository(store=store, index=index)
    )

    result = service.learn(
        target_story_id=story_id,
        snapshots=(snapshot(story_id, 10),),
        quality=quality(),
        asset=TrainingAsset(
            asset_id=story_id,
            rights_mode=RightsMode.REFERENCE_ONLY,
            source_uri="https://reddit.com/r/stories/external-story",
        ),
        content="Contenido externo",
    )

    assert result.decision.status == "rejected"
    assert result.decision.reason == "rights_not_reusable"
    assert index.retrieve(
        RetrievalQueryV3(
            "Contenido externo",
            now=1_900_000_000,
            language="es",
            scope="narrative",
            allowed_rights=("promoted_learning",),
        )
    ).results == ()
    store.close()
    index.close()
