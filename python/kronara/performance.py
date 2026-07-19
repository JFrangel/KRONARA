from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Iterable, Literal

from kronara.analytics import minimum_sample_size, wilson_interval


@dataclass(frozen=True)
class MetricSnapshot:
    schema_version: int
    snapshot_id: str
    content_id: str
    platform: str
    published_at: datetime
    observed_at: datetime
    metric_window_hours: int
    impressions: int
    starts: int
    completions: int
    replays: int
    shares: int
    watch_time_seconds: float
    duration_seconds: float
    voice_id: str
    topic: str
    hook_id: str
    publication_hour: int
    audience_segment: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported metric snapshot schema")
        required = (
            self.snapshot_id,
            self.content_id,
            self.platform,
            self.voice_id,
            self.topic,
            self.hook_id,
            self.audience_segment,
        )
        if any(not value.strip() for value in required):
            raise ValueError("metric snapshot identifiers are required")
        if self.observed_at < self.published_at:
            raise ValueError("observed_at cannot precede published_at")
        if self.metric_window_hours <= 0:
            raise ValueError("metric_window_hours must be positive")
        counts = (self.impressions, self.starts, self.completions, self.replays, self.shares)
        if any(value < 0 for value in counts):
            raise ValueError("metric counts cannot be negative")
        if self.starts > self.impressions:
            raise ValueError("starts cannot exceed impressions")
        if self.completions > self.starts:
            raise ValueError("completions cannot exceed starts")
        if self.watch_time_seconds < 0 or self.duration_seconds <= 0:
            raise ValueError("watch time and duration must be valid")
        if not 0 <= self.publication_hour <= 23:
            raise ValueError("publication_hour must be between 0 and 23")


@dataclass(frozen=True)
class SegmentFinding:
    dimension: str
    value: str
    pieces: int
    starts: int
    completions: int
    completion_rate: float
    interval: tuple[float, float]
    absolute_lift_vs_overall: float
    eligible: bool


@dataclass(frozen=True)
class PerformanceHypothesis:
    hypothesis_id: str
    dimension: str
    candidate_value: str
    statement: str
    baseline_rate: float
    candidate_rate: float
    absolute_lift: float
    causal_claim: bool
    minimum_sample_per_variant: int
    recommended_experiment: str


@dataclass(frozen=True)
class PerformanceDiagnosis:
    schema_version: int
    status: Literal["insufficient_data", "descriptive", "ready_for_experiment"]
    platform: str
    metric: str
    input_hash: str
    total_pieces: int
    total_starts: int
    overall_completion_rate: float | None
    overall_interval: tuple[float, float] | None
    segments: tuple[SegmentFinding, ...]
    hypotheses: tuple[PerformanceHypothesis, ...]
    warnings: tuple[str, ...]


class PerformanceScientist:
    def __init__(
        self,
        *,
        minimum_total_starts: int = 200,
        minimum_segment_starts: int = 100,
        minimum_segment_pieces: int = 2,
        minimum_lift: float = 0.03,
    ):
        if min(minimum_total_starts, minimum_segment_starts, minimum_segment_pieces) <= 0:
            raise ValueError("sample thresholds must be positive")
        if minimum_lift < 0:
            raise ValueError("minimum_lift cannot be negative")
        self.minimum_total_starts = minimum_total_starts
        self.minimum_segment_starts = minimum_segment_starts
        self.minimum_segment_pieces = minimum_segment_pieces
        self.minimum_lift = minimum_lift

    def diagnose(self, snapshots: Iterable[MetricSnapshot]) -> PerformanceDiagnosis:
        ordered = tuple(sorted(snapshots, key=lambda item: item.snapshot_id))
        input_hash = self._input_hash(ordered)
        if not ordered:
            return PerformanceDiagnosis(
                schema_version=1,
                status="insufficient_data",
                platform="unknown",
                metric="completion_rate",
                input_hash=input_hash,
                total_pieces=0,
                total_starts=0,
                overall_completion_rate=None,
                overall_interval=None,
                segments=(),
                hypotheses=(),
                warnings=("empty_sample", "observational_not_causal"),
            )

        platforms = {item.platform for item in ordered}
        if len(platforms) != 1:
            raise ValueError("diagnose one platform at a time; platform metrics cannot be pooled")
        platform = next(iter(platforms))
        total_starts = sum(item.starts for item in ordered)
        total_completions = sum(item.completions for item in ordered)
        overall_rate = total_completions / total_starts if total_starts else None
        overall_interval = (
            wilson_interval(total_completions, total_starts) if total_starts else None
        )

        dimensions: tuple[tuple[str, Callable[[MetricSnapshot], str]], ...] = (
            ("voice", lambda item: item.voice_id),
            ("topic", lambda item: item.topic),
            ("hook", lambda item: item.hook_id),
            ("duration", lambda item: self._duration_bucket(item.duration_seconds)),
            ("publication_time", lambda item: self._time_bucket(item.publication_hour)),
            ("audience", lambda item: item.audience_segment),
        )
        findings: list[SegmentFinding] = []
        hypotheses: list[PerformanceHypothesis] = []
        for dimension, selector in dimensions:
            groups: dict[str, list[MetricSnapshot]] = defaultdict(list)
            for snapshot in ordered:
                groups[selector(snapshot)].append(snapshot)
            dimension_findings: list[SegmentFinding] = []
            for value, items in sorted(groups.items()):
                starts = sum(item.starts for item in items)
                completions = sum(item.completions for item in items)
                rate = completions / starts if starts else 0.0
                eligible = (
                    starts >= self.minimum_segment_starts
                    and len(items) >= self.minimum_segment_pieces
                )
                finding = SegmentFinding(
                    dimension=dimension,
                    value=value,
                    pieces=len(items),
                    starts=starts,
                    completions=completions,
                    completion_rate=rate,
                    interval=wilson_interval(completions, starts) if starts else (0.0, 1.0),
                    absolute_lift_vs_overall=(rate - overall_rate) if overall_rate is not None else 0.0,
                    eligible=eligible,
                )
                findings.append(finding)
                dimension_findings.append(finding)
            eligible_findings = [item for item in dimension_findings if item.eligible]
            if (
                total_starts >= self.minimum_total_starts
                and len(eligible_findings) >= 2
                and overall_rate is not None
            ):
                candidate = max(eligible_findings, key=lambda item: (item.completion_rate, item.value))
                if candidate.absolute_lift_vs_overall >= self.minimum_lift:
                    hypotheses.append(self._hypothesis(platform, candidate, overall_rate))

        warnings = ["observational_not_causal"]
        if total_starts < self.minimum_total_starts:
            status = "insufficient_data"
            warnings.append("insufficient_total_sample")
            hypotheses = []
        elif hypotheses:
            status = "ready_for_experiment"
        else:
            status = "descriptive"
            warnings.append("no_material_segment_signal")
        return PerformanceDiagnosis(
            schema_version=1,
            status=status,
            platform=platform,
            metric="completion_rate",
            input_hash=input_hash,
            total_pieces=len(ordered),
            total_starts=total_starts,
            overall_completion_rate=overall_rate,
            overall_interval=overall_interval,
            segments=tuple(findings),
            hypotheses=tuple(hypotheses),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _hypothesis(
        platform: str,
        candidate: SegmentFinding,
        baseline_rate: float,
    ) -> PerformanceHypothesis:
        identity = f"{platform}:{candidate.dimension}:{candidate.value}:completion_rate"
        hypothesis_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return PerformanceHypothesis(
            hypothesis_id=hypothesis_id,
            dimension=candidate.dimension,
            candidate_value=candidate.value,
            statement=(
                f"En datos observacionales de {platform}, {candidate.dimension}={candidate.value} "
                "está asociada con una finalización superior; requiere experimento controlado."
            ),
            baseline_rate=baseline_rate,
            candidate_rate=candidate.completion_rate,
            absolute_lift=candidate.absolute_lift_vs_overall,
            causal_claim=False,
            minimum_sample_per_variant=minimum_sample_size(
                baseline_rate,
                max(candidate.absolute_lift_vs_overall, 0.01),
            ),
            recommended_experiment=(
                f"Comparar {candidate.dimension}={candidate.value} contra el baseline con asignación "
                "controlada, misma audiencia, duración y ventana de medición."
            ),
        )

    @staticmethod
    def _duration_bucket(duration_seconds: float) -> str:
        if duration_seconds <= 30:
            return "00-30s"
        if duration_seconds <= 60:
            return "31-60s"
        return "61s+"

    @staticmethod
    def _time_bucket(hour: int) -> str:
        start = (hour // 6) * 6
        return f"{start:02d}-{start + 5:02d}"

    @staticmethod
    def _input_hash(snapshots: tuple[MetricSnapshot, ...]) -> str:
        payload = []
        for snapshot in snapshots:
            item = asdict(snapshot)
            item["published_at"] = snapshot.published_at.isoformat()
            item["observed_at"] = snapshot.observed_at.isoformat()
            payload.append(item)
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
