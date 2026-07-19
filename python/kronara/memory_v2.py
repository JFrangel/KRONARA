from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from kronara.operations_contracts import MemoryRecord
from kronara.store import KronaraStore


_REUSABLE_RIGHTS = frozenset(
    {"owned_original", "licensed_training", "promoted_learning", "internal_operation"}
)
_ALLOWED_STATES = frozenset({"hypothesis", "testing", "supported", "promoted"})


@dataclass(frozen=True)
class MemoryCandidate:
    record_id: str
    kind: str
    scope: str
    content: str
    provenance_uri: str
    confidence: float
    rights_mode: str
    valid_from: int
    valid_until: int | None
    version: int
    evidence_refs: tuple[str, ...]
    proposed_status: str


@dataclass(frozen=True)
class MemoryDecision:
    record_id: str
    status: str
    reason: str
    record: MemoryRecord | None


class MemoryCurator:
    """Promotes explicit, evidenced memories without collapsing rival hypotheses."""

    def __init__(
        self,
        *,
        store: KronaraStore | None = None,
        now: Callable[[], int],
    ):
        self.store = store
        self.now = now

    def propose(self, candidate: MemoryCandidate) -> MemoryDecision:
        if candidate.rights_mode not in _REUSABLE_RIGHTS:
            return MemoryDecision(
                candidate.record_id, "rejected", "rights_not_reusable", None
            )
        if candidate.valid_until is not None and self.now() > candidate.valid_until:
            return MemoryDecision(candidate.record_id, "expired", "memory_expired", None)
        if candidate.proposed_status not in _ALLOWED_STATES:
            return MemoryDecision(
                candidate.record_id, "rejected", "unsupported_memory_status", None
            )
        try:
            record = MemoryRecord(
                record_id=candidate.record_id,
                kind=candidate.kind,
                scope=candidate.scope,
                content=candidate.content,
                provenance_uri=candidate.provenance_uri,
                confidence=candidate.confidence,
                rights_mode=candidate.rights_mode,
                valid_from=candidate.valid_from,
                valid_until=candidate.valid_until,
                version=candidate.version,
                evidence_refs=candidate.evidence_refs,
                status=candidate.proposed_status,
            )
        except ValueError:
            return MemoryDecision(
                candidate.record_id, "rejected", "invalid_memory_contract", None
            )
        if self.store is not None:
            self.store.save_memory(record)
        reason = (
            "stored_as_competing_hypothesis"
            if candidate.proposed_status == "hypothesis"
            else "memory_evidence_accepted"
        )
        return MemoryDecision(candidate.record_id, candidate.proposed_status, reason, record)

