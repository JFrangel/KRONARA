from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class NarrativeQualityReport:
    passed: bool
    total: float
    blocking_dimensions: tuple[str, ...]


class NarrativeQualityEvaluator:
    dimensions = (
        "hook",
        "clarity",
        "conflict",
        "escalation",
        "agency",
        "coherence",
        "credibility",
        "originality",
        "retention",
        "payoff",
        "production_fit",
    )

    def __init__(self, minimum_total: float = 80.0, minimum_dimension: float = 7.0):
        self.minimum_total = minimum_total
        self.minimum_dimension = minimum_dimension

    def evaluate(self, scores: Mapping[str, float]) -> NarrativeQualityReport:
        missing = tuple(item for item in self.dimensions if item not in scores)
        invalid = tuple(
            item for item in self.dimensions if item in scores and not 0 <= float(scores[item]) <= 10
        )
        blocking = tuple(
            item for item in self.dimensions if item not in scores or float(scores[item]) < self.minimum_dimension
        )
        total = sum(float(scores.get(item, 0)) for item in self.dimensions)
        return NarrativeQualityReport(
            passed=not missing and not invalid and not blocking and total >= self.minimum_total,
            total=total,
            blocking_dimensions=tuple(dict.fromkeys((*blocking, *invalid))),
        )

    @staticmethod
    def detect_antipatterns(text: str) -> tuple[str, ...]:
        patterns = {
            "dream_reset": r"(?i)todo era (solo )?un sue[ñn]o",
            "unseeded_twist": r"(?i)(de repente|sin ninguna pista previa).*(villano|culpable)|"
            r"(villano|culpable).*(sin ninguna pista previa)",
            "passive_protagonist": r"(?i)al final alguien (lo|la) salv[óo]",
            "copied_source": r"(?i)(copiar|repetir) (la historia|el post) (exactamente|palabra por palabra)",
        }
        return tuple(code for code, pattern in patterns.items() if re.search(pattern, text))
