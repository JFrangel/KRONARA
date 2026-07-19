from __future__ import annotations

from dataclasses import asdict, dataclass

from kronara.analytics import wilson_interval
from kronara.performance import MetricSnapshot, PerformanceDiagnosis, PerformanceScientist
from kronara.story_reuse import (
    OwnedStoryPerformance,
    StoryExampleRepository,
    StoryQualityEvidence,
    StoryReuseDecision,
    StoryReuseGate,
)
from kronara.training_rights import TrainingAsset


@dataclass(frozen=True)
class PerformanceLearningResult:
    diagnosis: PerformanceDiagnosis
    performance: OwnedStoryPerformance
    decision: StoryReuseDecision


class PerformanceLearningService:
    """Turns comparable snapshots into reversible learning, never causal claims."""

    def __init__(
        self,
        *,
        repository: StoryExampleRepository,
        scientist: PerformanceScientist | None = None,
        gate: StoryReuseGate | None = None,
    ):
        self.repository = repository
        self.scientist = scientist or PerformanceScientist()
        self.gate = gate or StoryReuseGate()

    def learn(
        self,
        *,
        target_story_id: str,
        snapshots: tuple[MetricSnapshot, ...],
        quality: StoryQualityEvidence,
        asset: TrainingAsset,
        content: str,
    ) -> PerformanceLearningResult:
        latest = self._latest_by_content(snapshots)
        diagnosis = self.scientist.diagnose(latest)
        target = next(
            (item for item in latest if item.content_id == target_story_id),
            None,
        )
        if target is None:
            raise ValueError("target story metrics are required")
        cohort = tuple(
            item
            for item in latest
            if item.content_id != target_story_id and self._comparable(target, item)
        )
        performance = self._performance(target, cohort)
        decision = self.gate.evaluate(performance, quality, asset)
        if decision.status == "rag_candidate":
            decision = self.repository.promote(decision, content=content)
        else:
            self.repository.store.save_story_reuse_decision(
                decision.story_id, decision.status, asdict(decision)
            )
        return PerformanceLearningResult(diagnosis, performance, decision)

    @staticmethod
    def _latest_by_content(
        snapshots: tuple[MetricSnapshot, ...],
    ) -> tuple[MetricSnapshot, ...]:
        latest: dict[str, MetricSnapshot] = {}
        for snapshot in snapshots:
            current = latest.get(snapshot.content_id)
            if current is None or (snapshot.observed_at, snapshot.snapshot_id) > (
                current.observed_at,
                current.snapshot_id,
            ):
                latest[snapshot.content_id] = snapshot
        return tuple(sorted(latest.values(), key=lambda item: item.snapshot_id))

    @staticmethod
    def _comparable(target: MetricSnapshot, candidate: MetricSnapshot) -> bool:
        duration_delta = abs(candidate.duration_seconds - target.duration_seconds)
        return (
            candidate.platform == target.platform
            and candidate.audience_segment == target.audience_segment
            and candidate.metric_window_hours == target.metric_window_hours
            and duration_delta <= max(3.0, target.duration_seconds * 0.10)
        )

    @staticmethod
    def _performance(
        target: MetricSnapshot,
        cohort: tuple[MetricSnapshot, ...],
    ) -> OwnedStoryPerformance:
        target_rate = target.completions / target.starts if target.starts else 0.0
        baseline_starts = sum(item.starts for item in cohort)
        baseline_completions = sum(item.completions for item in cohort)
        baseline_rate = baseline_completions / baseline_starts if baseline_starts else 0.0
        target_interval = (
            wilson_interval(target.completions, target.starts)
            if target.starts
            else (0.0, 1.0)
        )
        baseline_interval = (
            wilson_interval(baseline_completions, baseline_starts)
            if baseline_starts
            else (0.0, 1.0)
        )
        relative_lift = (
            (target_rate - baseline_rate) / baseline_rate
            if baseline_rate > 0
            else 0.0
        )
        total_starts = target.starts + baseline_starts
        return OwnedStoryPerformance(
            story_id=target.content_id,
            platform=target.platform,
            format="reel",
            sample_size=target.starts,
            metric_window_hours=target.metric_window_hours,
            relative_lift=relative_lift,
            confidence_low=target_interval[0] - baseline_interval[1],
            confidence_high=target_interval[1] - baseline_interval[0],
            comparable_cohort=len(cohort) >= 2 and baseline_starts > 0,
            outlier_share=(target.starts / total_starts if total_starts else 1.0),
            reputational_risk="low",
            evidence_refs=tuple(item.snapshot_id for item in (target, *cohort)),
        )
