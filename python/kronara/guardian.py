from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from kronara.contracts import EvidenceRef


@dataclass(frozen=True)
class GuardianReport:
    passed: bool
    unverified_claims: tuple[str, ...] = ()


class Guardian:
    def verify_claims(
        self, claims: Iterable[str], evidence: Iterable[EvidenceRef]
    ) -> GuardianReport:
        supported = {
            claim
            for item in evidence
            if item.confidence >= 0.7
            for claim in item.supports
        }
        missing = tuple(claim for claim in claims if claim not in supported)
        return GuardianReport(passed=not missing, unverified_claims=missing)

