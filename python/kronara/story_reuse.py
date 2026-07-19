from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal, Protocol

from kronara.store import KronaraStore
from kronara.training_rights import TrainingAsset, TrainingRightsPolicy


@dataclass(frozen=True)
class OwnedStoryPerformance:
    story_id: str
    platform: str
    format: str
    sample_size: int
    metric_window_hours: int
    relative_lift: float
    confidence_low: float
    confidence_high: float
    comparable_cohort: bool
    outlier_share: float
    reputational_risk: Literal["low", "medium", "high", "critical"]
    evidence_refs: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported owned story performance schema")
        if not self.story_id or not self.platform or not self.format:
            raise ValueError("story performance identity is required")
        if self.sample_size < 0 or self.metric_window_hours < 1:
            raise ValueError("story performance sample and window are invalid")
        if self.confidence_low > self.confidence_high:
            raise ValueError("story performance confidence interval is invalid")
        if not 0 <= self.outlier_share <= 1:
            raise ValueError("story outlier share must be between zero and one")
        if not self.evidence_refs:
            raise ValueError("story performance evidence is required")


@dataclass(frozen=True)
class StoryQualityEvidence:
    narrative_passed: bool
    originality_passed: bool
    safety_passed: bool
    publication_succeeded: bool
    golden_no_regression: bool
    evidence_refs: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(
            (
                self.narrative_passed,
                self.originality_passed,
                self.safety_passed,
                self.publication_succeeded,
                self.golden_no_regression,
            )
        ) and bool(self.evidence_refs)


@dataclass(frozen=True)
class StoryReuseDecision:
    schema_version: int
    story_id: str
    status: Literal[
        "eligible_owned",
        "measuring",
        "supported_example",
        "rag_candidate",
        "promoted_rag_example",
        "dataset_candidate",
        "approved_training_example",
        "rejected",
        "reverted",
    ]
    reason: str
    automatic_action: str | None
    requires_administrative_approval: bool
    reversible: bool
    evidence_refs: tuple[str, ...]


class StoryReuseGate:
    def __init__(
        self,
        *,
        rights_policy: TrainingRightsPolicy | None = None,
        minimum_sample: int = 100,
        minimum_relative_lift: float = 0.05,
        maximum_outlier_share: float = 0.5,
        training_candidate_sample: int = 1000,
        training_candidate_lift: float = 0.10,
    ):
        self.rights_policy = rights_policy or TrainingRightsPolicy()
        self.minimum_sample = minimum_sample
        self.minimum_relative_lift = minimum_relative_lift
        self.maximum_outlier_share = maximum_outlier_share
        self.training_candidate_sample = training_candidate_sample
        self.training_candidate_lift = training_candidate_lift

    def evaluate(
        self,
        performance: OwnedStoryPerformance,
        quality: StoryQualityEvidence,
        asset: TrainingAsset,
    ) -> StoryReuseDecision:
        rights = self.rights_policy.decide(asset, commercial_use=True)
        evidence = tuple(
            dict.fromkeys(
                (*performance.evidence_refs, *quality.evidence_refs, rights.evidence_uri)
            )
        )
        evidence = tuple(item for item in evidence if item)
        if asset.asset_id != performance.story_id or not rights.allowed:
            return self._decision(
                performance.story_id, "rejected", "rights_not_reusable", evidence
            )
        if not quality.passed:
            return self._decision(
                performance.story_id, "rejected", "quality_gate_failed", evidence
            )
        if performance.reputational_risk in {"high", "critical"}:
            return self._decision(
                performance.story_id, "rejected", "reputational_risk", evidence
            )
        if performance.sample_size < self.minimum_sample or not performance.comparable_cohort:
            return self._decision(
                performance.story_id,
                "measuring",
                "insufficient_comparable_sample",
                evidence,
            )
        if performance.outlier_share > self.maximum_outlier_share:
            return self._decision(
                performance.story_id, "measuring", "outlier_dominance", evidence
            )
        if (
            performance.relative_lift < self.minimum_relative_lift
            or performance.confidence_low <= 0
        ):
            return self._decision(
                performance.story_id, "measuring", "effect_not_supported", evidence
            )
        if (
            performance.sample_size >= self.training_candidate_sample
            and performance.relative_lift >= self.training_candidate_lift
        ):
            return StoryReuseDecision(
                schema_version=1,
                story_id=performance.story_id,
                status="dataset_candidate",
                reason="owned_example_ready_for_admin_review",
                automatic_action=None,
                requires_administrative_approval=True,
                reversible=False,
                evidence_refs=evidence,
            )
        return StoryReuseDecision(
            schema_version=1,
            story_id=performance.story_id,
            status="rag_candidate",
            reason="owned_quality_and_performance_supported",
            automatic_action="promote_rag_example",
            requires_administrative_approval=False,
            reversible=True,
            evidence_refs=evidence,
        )

    @staticmethod
    def _decision(
        story_id: str,
        status: Literal["measuring", "rejected"],
        reason: str,
        evidence_refs: tuple[str, ...],
    ) -> StoryReuseDecision:
        return StoryReuseDecision(
            schema_version=1,
            story_id=story_id,
            status=status,
            reason=reason,
            automatic_action=None,
            requires_administrative_approval=False,
            reversible=False,
            evidence_refs=evidence_refs,
        )


class StoryIndex(Protocol):
    def promote_owned_story(
        self, story_id: str, content: str, evidence_refs: tuple[str, ...]
    ) -> None: ...

    def tombstone(self, story_id: str) -> None: ...


class StoryExampleRepository:
    def __init__(self, *, store: KronaraStore, index: StoryIndex):
        self.store = store
        self.index = index

    def promote(
        self,
        decision: StoryReuseDecision,
        *,
        content: str,
    ) -> StoryReuseDecision:
        if decision.status != "rag_candidate" or decision.automatic_action != "promote_rag_example":
            raise ValueError("only an approved RAG candidate can be promoted")
        if not content.strip():
            raise ValueError("owned story content is required")
        self.index.promote_owned_story(
            decision.story_id, content, decision.evidence_refs
        )
        promoted = replace(
            decision,
            status="promoted_rag_example",
            reason="promoted_to_reversible_rag_example",
            automatic_action=None,
        )
        self.store.save_story_reuse_decision(
            promoted.story_id, promoted.status, asdict(promoted)
        )
        return promoted

    def revert(self, story_id: str, reason: str) -> StoryReuseDecision:
        if not reason.strip():
            raise ValueError("reversion reason is required")
        current = self.store.load_story_reuse_decision(story_id)
        if current.get("status") != "promoted_rag_example":
            raise ValueError("only a promoted RAG example can be reverted")
        self.index.tombstone(story_id)
        reverted = StoryReuseDecision(
            schema_version=1,
            story_id=story_id,
            status="reverted",
            reason=reason,
            automatic_action=None,
            requires_administrative_approval=False,
            reversible=False,
            evidence_refs=tuple(current.get("evidence_refs", ())),
        )
        self.store.save_story_reuse_decision(
            story_id, reverted.status, asdict(reverted)
        )
        return reverted

