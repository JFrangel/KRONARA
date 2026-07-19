from kronara.store import KronaraStore
from kronara.story_reuse import (
    OwnedStoryPerformance,
    StoryQualityEvidence,
    StoryExampleRepository,
    StoryReuseGate,
)
from kronara.training_rights import RightsMode, TrainingAsset


def performance(**overrides) -> OwnedStoryPerformance:
    values = {
        "story_id": "story_1",
        "platform": "facebook",
        "format": "reel",
        "sample_size": 250,
        "metric_window_hours": 72,
        "relative_lift": 0.12,
        "confidence_low": 0.05,
        "confidence_high": 0.19,
        "comparable_cohort": True,
        "outlier_share": 0.1,
        "reputational_risk": "low",
        "evidence_refs": ("metric_1",),
    }
    values.update(overrides)
    return OwnedStoryPerformance(**values)


def quality(**overrides) -> StoryQualityEvidence:
    values = {
        "narrative_passed": True,
        "originality_passed": True,
        "safety_passed": True,
        "publication_succeeded": True,
        "golden_no_regression": True,
        "evidence_refs": ("qc_1", "originality_1"),
    }
    values.update(overrides)
    return StoryQualityEvidence(**values)


def owned_asset() -> TrainingAsset:
    return TrainingAsset(
        asset_id="story_1",
        rights_mode=RightsMode.OWNED_ORIGINAL,
        source_uri="kronara://artifacts/story_1",
    )


def reference_asset() -> TrainingAsset:
    return TrainingAsset(
        asset_id="reddit_1",
        rights_mode=RightsMode.REFERENCE_ONLY,
        source_uri="https://reddit.com/r/stories/1",
    )


def test_owned_story_with_comparable_metrics_can_be_promoted_to_rag():
    decision = StoryReuseGate().evaluate(performance(), quality(), owned_asset())

    assert decision.status == "rag_candidate"
    assert decision.automatic_action == "promote_rag_example"
    assert decision.reversible
    assert not decision.requires_administrative_approval


def test_reference_story_and_single_outlier_are_never_promoted():
    reference = StoryReuseGate().evaluate(performance(), quality(), reference_asset())
    outlier = StoryReuseGate().evaluate(
        performance(outlier_share=0.8), quality(), owned_asset()
    )

    assert reference.status == "rejected"
    assert reference.reason == "rights_not_reusable"
    assert outlier.status == "measuring"
    assert outlier.reason == "outlier_dominance"


def test_fine_tuning_candidate_requires_admin_even_for_owned_story():
    decision = StoryReuseGate().evaluate(
        performance(sample_size=1500, relative_lift=0.2),
        quality(),
        owned_asset(),
    )

    assert decision.status == "dataset_candidate"
    assert decision.automatic_action is None
    assert decision.requires_administrative_approval


def test_quality_regression_and_insufficient_sample_fail_closed():
    unsafe = StoryReuseGate().evaluate(
        performance(), quality(safety_passed=False), owned_asset()
    )
    small = StoryReuseGate().evaluate(
        performance(sample_size=20), quality(), owned_asset()
    )

    assert unsafe.status == "rejected"
    assert unsafe.reason == "quality_gate_failed"
    assert small.status == "measuring"
    assert small.reason == "insufficient_comparable_sample"


class RecordingIndex:
    def __init__(self):
        self.promoted = []
        self.tombstoned = []

    def promote_owned_story(self, story_id, content, evidence_refs):
        self.promoted.append((story_id, content, evidence_refs))

    def tombstone(self, story_id):
        self.tombstoned.append(story_id)


def test_repository_persists_promotion_and_reverts_with_tombstone(tmp_path):
    store = KronaraStore(tmp_path / "reuse.db")
    store.initialize()
    index = RecordingIndex()
    repository = StoryExampleRepository(store=store, index=index)
    decision = StoryReuseGate().evaluate(performance(), quality(), owned_asset())

    promoted = repository.promote(
        decision,
        content="Historia propia completa",
    )
    reverted = repository.revert("story_1", "quality regression")

    assert promoted.status == "promoted_rag_example"
    assert reverted.status == "reverted"
    assert index.promoted[0][0] == "story_1"
    assert index.tombstoned == ["story_1"]
    assert store.load_story_reuse_decision("story_1")["status"] == "reverted"
    store.close()

