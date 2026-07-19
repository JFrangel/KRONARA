from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Any


class AnalysisInputError(ValueError):
    pass


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0 or successes < 0 or successes > total:
        raise AnalysisInputError("Wilson interval requires valid successes and denominator")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def minimum_sample_size(
    baseline_rate: float,
    minimum_detectable_absolute_lift: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    treatment_rate = baseline_rate + minimum_detectable_absolute_lift
    if not 0 < baseline_rate < 1:
        raise AnalysisInputError("baseline_rate must be between zero and one")
    if minimum_detectable_absolute_lift <= 0 or treatment_rate >= 1:
        raise AnalysisInputError("detectable lift must be positive and keep treatment below one")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise AnalysisInputError("alpha and power must be between zero and one")
    normal = statistics.NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power = normal.inv_cdf(power)
    pooled = (baseline_rate + treatment_rate) / 2
    numerator = (
        z_alpha * math.sqrt(2 * pooled * (1 - pooled))
        + z_power
        * math.sqrt(
            baseline_rate * (1 - baseline_rate)
            + treatment_rate * (1 - treatment_rate)
        )
    ) ** 2
    return math.ceil(numerator / (minimum_detectable_absolute_lift**2))


@dataclass(frozen=True)
class AnalysisRequest:
    operation: str
    inputs: dict[str, Any]
    unit: str | None = None
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisTrace:
    operation: str
    input_hash: str
    result: dict[str, Any]
    unit: str | None
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)


class AnalyticalToolkit:
    """Closed deterministic analytics registry; it never evaluates arbitrary code."""

    def execute(self, request: AnalysisRequest) -> AnalysisTrace:
        operations = {
            "describe": self._describe,
            "compare_rates": self._compare_rates,
            "funnel": self._funnel,
            "robust_outliers": self._robust_outliers,
            "retention_curve": self._retention_curve,
            "minimum_sample_size": self._minimum_sample_size,
        }
        operation = operations.get(request.operation)
        if operation is None:
            raise AnalysisInputError(f"unsupported operation: {request.operation}")
        result, warnings = operation(request.inputs)
        normalized = json.dumps(
            {"operation": request.operation, "inputs": request.inputs, "unit": request.unit},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return AnalysisTrace(
            operation=request.operation,
            input_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            result=result,
            unit=request.unit,
            assumptions=request.assumptions,
            warnings=warnings,
        )

    def _describe(self, inputs: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
        raw = self._list(inputs, "values")
        values = self._finite_values(raw)
        if not values:
            raise AnalysisInputError("values contain no finite observations")
        return (
            {
                "count": len(values),
                "missing": len(raw) - len(values),
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
                "minimum": min(values),
                "maximum": max(values),
            },
            (),
        )

    def _compare_rates(
        self, inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        baseline_successes, baseline_total = self._rate_pair(inputs, "baseline")
        treatment_successes, treatment_total = self._rate_pair(inputs, "treatment")
        baseline = baseline_successes / baseline_total
        treatment = treatment_successes / treatment_total
        absolute = treatment - baseline
        relative = absolute / baseline if baseline > 0 else None
        warnings = ("baseline_zero_relative_lift_undefined",) if relative is None else ()
        return (
            {
                "baseline_rate": baseline,
                "treatment_rate": treatment,
                "absolute_lift": absolute,
                "relative_lift": relative,
                "baseline_interval": self._wilson(baseline_successes, baseline_total),
                "treatment_interval": self._wilson(treatment_successes, treatment_total),
            },
            warnings,
        )

    def _funnel(self, inputs: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
        stages = self._list(inputs, "stages")
        if len(stages) < 2:
            raise AnalysisInputError("funnel requires at least two stages")
        parsed: list[tuple[str, float]] = []
        for item in stages:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise AnalysisInputError("each funnel stage must contain name and value")
            name, raw_value = item
            value = self._finite_number(raw_value, "funnel stage")
            if value < 0:
                raise AnalysisInputError("funnel stage cannot be negative")
            parsed.append((str(name), value))
        transitions: list[dict[str, Any]] = []
        warnings = ["descriptive_not_causal"]
        for (source_name, source), (target_name, target) in zip(parsed, parsed[1:]):
            if source <= 0:
                raise AnalysisInputError("funnel denominator must be positive")
            conversion = target / source
            if target > source:
                warnings.append("funnel_stage_increase")
            transitions.append(
                {
                    "from": source_name,
                    "to": target_name,
                    "conversion_rate": conversion,
                    "dropoff_rate": 1.0 - conversion,
                }
            )
        first = parsed[0][1]
        if first <= 0:
            raise AnalysisInputError("funnel denominator must be positive")
        return (
            {
                "overall_conversion": parsed[-1][1] / first,
                "transitions": transitions,
            },
            tuple(dict.fromkeys(warnings)),
        )

    def _robust_outliers(
        self, inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        values = self._finite_values(self._list(inputs, "values"))
        if len(values) < 3:
            raise AnalysisInputError("robust outliers require at least three values")
        median = float(statistics.median(values))
        deviations = [abs(value - median) for value in values]
        mad = float(statistics.median(deviations))
        if mad == 0:
            outliers = [value for value in values if value != median]
            warnings = ("zero_median_absolute_deviation",)
        else:
            outliers = [
                value for value in values if 0.6745 * abs(value - median) / mad > 3.5
            ]
            warnings = ()
        return ({"median": median, "mad": mad, "outliers": outliers}, warnings)

    def _retention_curve(
        self, inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        starts = inputs.get("starts")
        if not isinstance(starts, int) or starts <= 0:
            raise AnalysisInputError("retention starts must be a positive integer")
        duration = self._finite_number(inputs.get("duration_seconds"), "duration_seconds")
        if duration <= 0:
            raise AnalysisInputError("duration_seconds must be positive")
        raw_checkpoints = self._list(inputs, "checkpoints")
        if len(raw_checkpoints) < 2:
            raise AnalysisInputError("retention curve requires at least two checkpoints")
        points: list[dict[str, Any]] = []
        previous_second = -1.0
        previous_viewers = float(starts)
        dropoffs: list[dict[str, float]] = []
        for raw in raw_checkpoints:
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                raise AnalysisInputError("each retention checkpoint must contain second and viewers")
            second = self._finite_number(raw[0], "retention second")
            viewers = self._finite_number(raw[1], "retention viewers")
            if second <= previous_second or second < 0 or second > duration:
                raise AnalysisInputError("retention checkpoints must increase within duration")
            if viewers < 0 or viewers > starts or viewers > previous_viewers:
                raise AnalysisInputError("retention viewers must be non-increasing within starts")
            points.append(
                {
                    "second": second,
                    "viewers": viewers,
                    "retention_rate": viewers / starts,
                }
            )
            if previous_second >= 0:
                dropoffs.append(
                    {
                        "from_second": previous_second,
                        "to_second": second,
                        "absolute_viewer_drop": previous_viewers - viewers,
                        "dropoff_rate_from_starts": (previous_viewers - viewers) / starts,
                    }
                )
            previous_second = second
            previous_viewers = viewers
        largest = max(dropoffs, key=lambda item: item["absolute_viewer_drop"])
        return (
            {
                "points": points,
                "largest_dropoff": largest,
                "completion_rate": points[-1]["retention_rate"],
            },
            ("descriptive_not_causal",),
        )

    def _minimum_sample_size(
        self, inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        baseline = self._finite_number(inputs.get("baseline_rate"), "baseline_rate")
        lift = self._finite_number(
            inputs.get("minimum_detectable_absolute_lift"),
            "minimum_detectable_absolute_lift",
        )
        alpha = self._finite_number(inputs.get("alpha", 0.05), "alpha")
        power = self._finite_number(inputs.get("power", 0.8), "power")
        per_variant = minimum_sample_size(baseline, lift, alpha=alpha, power=power)
        return (
            {
                "per_variant": per_variant,
                "total_for_two_variants": per_variant * 2,
                "baseline_rate": baseline,
                "minimum_detectable_absolute_lift": lift,
                "alpha": alpha,
                "power": power,
            },
            ("approximate_two_proportion_design",),
        )

    def _rate_pair(self, inputs: dict[str, Any], prefix: str) -> tuple[int, int]:
        successes = inputs.get(f"{prefix}_successes")
        total = inputs.get(f"{prefix}_total")
        if not isinstance(successes, int) or not isinstance(total, int) or total <= 0:
            raise AnalysisInputError(f"{prefix} denominator must be a positive integer")
        if successes < 0 or successes > total:
            raise AnalysisInputError(f"{prefix} successes must be within denominator")
        return successes, total

    @staticmethod
    def _wilson(successes: int, total: int, z: float = 1.96) -> list[float]:
        return list(wilson_interval(successes, total, z))

    @staticmethod
    def _list(inputs: dict[str, Any], key: str) -> list[Any]:
        value = inputs.get(key)
        if not isinstance(value, list):
            raise AnalysisInputError(f"{key} must be a list")
        return value

    def _finite_values(self, raw: list[Any]) -> list[float]:
        values: list[float] = []
        for value in raw:
            if value is None:
                continue
            values.append(self._finite_number(value, "value"))
        return values

    @staticmethod
    def _finite_number(value: Any, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnalysisInputError(f"{label} must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise AnalysisInputError(f"{label} must be finite")
        return number
