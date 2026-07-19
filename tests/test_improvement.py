from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kronara.improvement import (
    CandidateEvaluation,
    CandidateVersion,
    DatasetCardBuilder,
    DatasetRightsError,
    ErrorMemory,
    EvaluationSet,
    ImprovementEngine,
    LearningHypothesis,
    TrainingExample,
)
from kronara.store import KronaraStore
from kronara.training_rights import RightsMode, TrainingAsset


NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_unfrozen_evaluation_set_never_promotes():
    decision = ImprovementEngine().evaluate(
        _candidate("champion-v1"),
        _candidate("challenger-v2"),
        _evaluation(frozen=False),
    )

    assert decision.status == "rejected"
    assert decision.reason == "evaluation_set_not_frozen"


def test_small_sample_remains_testing_even_with_large_lift():
    decision = ImprovementEngine(minimum_sample=100).evaluate(
        _candidate("champion-v1"),
        _candidate("challenger-v2"),
        _evaluation(sample_size=20, champion_score=0.4, challenger_score=0.8),
    )

    assert decision.status == "testing"
    assert decision.reason == "insufficient_sample"


def test_safety_regression_rejects_challenger_before_quality_lift():
    decision = ImprovementEngine().evaluate(
        _candidate("champion-v1"),
        _candidate("challenger-v2"),
        _evaluation(safety_regressions=("rights_bypass",), challenger_score=0.9),
    )

    assert decision.status == "rejected"
    assert decision.reason == "safety_regression"


def test_bounded_automatic_change_promotes_and_can_roll_back(tmp_path: Path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    engine = ImprovementEngine(store=store, minimum_relative_lift=0.05)
    champion = _candidate("champion-v1", parameter="voice_id")
    challenger = _candidate("challenger-v2", parameter="voice_id")

    decision = engine.evaluate(champion, challenger, _evaluation())
    receipt = engine.rollback("challenger-v2", "retention_regression_after_release")

    assert decision.status == "promoted"
    assert decision.authority_required == "automatic"
    assert decision.reversible is True
    assert receipt.status == "rolled_back"
    assert receipt.restored_version == "champion-v1"
    persisted = store.load_improvement_decision("challenger-v2")
    assert persisted["status"] == "rolled_back"


@pytest.mark.parametrize(
    ("parameter", "authority"),
    (("system_prompt", "supervised"), ("rights_policy", "administrative")),
)
def test_sensitive_change_requires_authority_even_when_quality_improves(parameter, authority):
    decision = ImprovementEngine().evaluate(
        _candidate("champion-v1", parameter=parameter),
        _candidate("challenger-v2", parameter=parameter),
        _evaluation(),
    )

    assert decision.status == "requires_approval"
    assert decision.authority_required == authority


def test_expired_candidate_is_rejected():
    decision = ImprovementEngine(now=lambda: NOW).evaluate(
        _candidate("champion-v1"),
        _candidate("challenger-v2", expires_at=NOW - timedelta(seconds=1)),
        _evaluation(),
    )

    assert decision.status == "rejected"
    assert decision.reason == "candidate_expired"


def test_dataset_card_rejects_reference_only_story_and_accepts_owned_script():
    reference = TrainingExample(
        example_id="reddit-story",
        asset=TrainingAsset(
            asset_id="reddit-story",
            rights_mode=RightsMode.REFERENCE_ONLY,
            source_uri="https://reddit.com/r/stories/1",
        ),
        split="train",
    )
    with pytest.raises(DatasetRightsError, match="REFERENCE_ONLY"):
        DatasetCardBuilder().build("dataset-1", (reference,), commercial_use=True)

    owned = TrainingExample(
        example_id="owned-script",
        asset=TrainingAsset(
            asset_id="owned-script",
            rights_mode=RightsMode.OWNED_ORIGINAL,
            source_uri="kronara://artifacts/owned-script",
        ),
        split="train",
    )
    card = DatasetCardBuilder().build("dataset-1", (owned,), commercial_use=True)

    assert card.example_count == 1
    assert card.split_counts == (("train", 1),)
    assert len(card.manifest_hash) == 64
    assert card.rights_modes == ("owned_original",)


def test_error_memory_and_competing_hypotheses_persist_without_overwrite(tmp_path: Path):
    database = tmp_path / "kronara.db"
    store = KronaraStore(database)
    store.initialize()
    engine = ImprovementEngine(store=store, now=lambda: NOW)
    engine.record_error(
        ErrorMemory(
            error_id="error-1",
            taxonomy="evidence.coverage",
            task_type="research",
            signature="missing independent source",
            evidence_uri="kronara://runs/run-1/evidence",
            occurred_at=NOW,
        )
    )
    engine.record_hypothesis(
        LearningHypothesis(
            hypothesis_id="hypothesis-a",
            statement="La voz A está asociada con mejor finalización.",
            state="testing",
            evidence_ids=("metric-1",),
            rival_ids=("hypothesis-b",),
            valid_until=NOW + timedelta(days=30),
        )
    )
    engine.record_hypothesis(
        LearningHypothesis(
            hypothesis_id="hypothesis-b",
            statement="El tema, no la voz, explica la diferencia.",
            state="testing",
            evidence_ids=("metric-2",),
            rival_ids=("hypothesis-a",),
            valid_until=NOW + timedelta(days=30),
        )
    )
    engine.resolve_error("error-1", "challenger-v2")
    store.close()

    reopened = KronaraStore(database)
    reopened.initialize()
    error = reopened.load_error_memory("error-1")
    hypotheses = reopened.list_learning_hypotheses()

    assert error["resolved_by_version"] == "challenger-v2"
    assert {item["hypothesis_id"] for item in hypotheses} == {
        "hypothesis-a",
        "hypothesis-b",
    }
    assert hypotheses[0]["rival_ids"]


def _candidate(
    version_id: str,
    *,
    parameter: str = "voice_id",
    expires_at: datetime | None = None,
) -> CandidateVersion:
    return CandidateVersion(
        version_id=version_id,
        parameter=parameter,
        config_hash=f"hash-{version_id}",
        created_at=NOW - timedelta(days=1),
        expires_at=expires_at or NOW + timedelta(days=30),
    )


def _evaluation(
    *,
    frozen: bool = True,
    sample_size: int = 500,
    champion_score: float = 0.5,
    challenger_score: float = 0.6,
    safety_regressions: tuple[str, ...] = (),
) -> CandidateEvaluation:
    return CandidateEvaluation(
        evaluation_id="evaluation-1",
        evaluation_set=EvaluationSet(
            set_id="golden-1",
            version=1,
            frozen=frozen,
            content_hash="golden-hash",
            case_count=100,
        ),
        sample_size=sample_size,
        champion_score=champion_score,
        challenger_score=challenger_score,
        safety_regressions=safety_regressions,
        cost_change_ratio=0.05,
        platform_stability=0.95,
    )
