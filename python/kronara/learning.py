from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LearningState(StrEnum):
    HYPOTHESIS = "hypothesis"
    TESTING = "testing"
    SUPPORTED = "supported"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ExperimentResult:
    hypothesis_id: str
    sample_size: int
    baseline_completion: float
    treatment_completion: float


@dataclass(frozen=True)
class LearningDecision:
    state: LearningState
    reason: str
    relative_lift: float


class LearningEngine:
    def __init__(self, minimum_sample: int = 100, minimum_lift: float = 0.05):
        self.minimum_sample = minimum_sample
        self.minimum_lift = minimum_lift

    def evaluate(self, result: ExperimentResult) -> LearningDecision:
        baseline = result.baseline_completion
        relative_lift = (
            (result.treatment_completion - baseline) / baseline if baseline > 0 else 0.0
        )
        if result.sample_size < self.minimum_sample:
            return LearningDecision(LearningState.TESTING, "insufficient_sample", relative_lift)
        if relative_lift >= self.minimum_lift:
            return LearningDecision(LearningState.PROMOTED, "material_retention_gain", relative_lift)
        return LearningDecision(LearningState.REJECTED, "no_material_gain", relative_lift)

