from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable

from kronara.research_contracts import (
    Contradiction,
    EvidenceClaim,
    EvidenceMatrix,
    ResearchCoverage,
    SourceRecord,
)


class EvidenceEngine:
    def __init__(self, now: datetime | None = None):
        self.now = now or datetime.now(UTC)

    def build(
        self,
        records: Iterable[SourceRecord],
        expected_subquestion_ids: tuple[str, ...] = (),
    ) -> EvidenceMatrix:
        accepted: list[SourceRecord] = []
        warnings: list[str] = []
        for record in records:
            if record.rights_mode in {"denied", "unknown"}:
                warnings.append(f"rights_rejected:{record.record_id}")
                continue
            if record.valid_until is not None and record.valid_until < self.now:
                warnings.append(f"expired:{record.record_id}")
                continue
            accepted.append(record)

        by_claim: dict[str, list[tuple[SourceRecord, object]]] = defaultdict(list)
        for record in accepted:
            for assertion in record.assertions:
                by_claim[assertion.claim_id].append((record, assertion))

        parent = {record.record_id: record.record_id for record in accepted}

        def find(record_id: str) -> str:
            while parent[record_id] != record_id:
                parent[record_id] = parent[parent[record_id]]
                record_id = parent[record_id]
            return record_id

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        by_family: dict[str, list[str]] = defaultdict(list)
        for record in accepted:
            by_family[record.source_family].append(record.record_id)
            for dependency in record.depends_on:
                if dependency in parent:
                    union(record.record_id, dependency)
        for record_ids in by_family.values():
            for record_id in record_ids[1:]:
                union(record_ids[0], record_id)

        claims: list[EvidenceClaim] = []
        contradictions: list[Contradiction] = []
        for claim_id in sorted(by_claim):
            entries = by_claim[claim_id]
            first_assertion = entries[0][1]
            support = tuple(record.record_id for record, assertion in entries if assertion.stance == "support")
            oppose = tuple(record.record_id for record, assertion in entries if assertion.stance == "oppose")
            independent_roots = {find(record.record_id) for record, _ in entries}
            confidence = sum(assertion.confidence for _, assertion in entries) / len(entries)
            if support and oppose:
                status = "contested"
                confidence *= 0.65
                contradictions.append(
                    Contradiction(
                        claim_id=claim_id,
                        supporting_source_ids=support,
                        opposing_source_ids=oppose,
                    )
                )
            elif support and len(independent_roots) >= 2:
                status = "supported"
            elif support:
                status = "weak"
                confidence *= 0.8
            else:
                status = "opposed"
                confidence *= 0.5
            claims.append(
                EvidenceClaim(
                    claim_id=claim_id,
                    subquestion_id=first_assertion.subquestion_id,
                    text=first_assertion.text,
                    kind=first_assertion.kind,
                    status=status,
                    supporting_source_ids=support,
                    opposing_source_ids=oppose,
                    independent_source_count=len(independent_roots),
                    confidence=round(confidence, 4),
                )
            )

        seen_subquestions = {item.subquestion_id for item in claims}
        expected = tuple(dict.fromkeys(expected_subquestion_ids))
        if expected:
            covered = tuple(item for item in expected if item in seen_subquestions)
            missing = tuple(item for item in expected if item not in seen_subquestions)
            ratio = len(covered) / len(expected)
        else:
            covered = tuple(sorted(seen_subquestions))
            missing = ()
            ratio = 1.0 if covered else 0.0
        coverage = ResearchCoverage(
            ratio=round(ratio, 4),
            complete=bool(covered) and not missing,
            covered_subquestion_ids=covered,
            missing_subquestion_ids=missing,
        )

        components: dict[str, list[str]] = defaultdict(list)
        for record in accepted:
            components[find(record.record_id)].append(record.record_id)
        dependent_groups = tuple(
            tuple(sorted(ids))
            for _, ids in sorted(components.items())
            if len(ids) > 1
        )
        source_uris = tuple(dict.fromkeys(record.source_uri for record in accepted))
        return EvidenceMatrix(
            schema_version=1,
            claims=tuple(claims),
            contradictions=tuple(contradictions),
            coverage=coverage,
            dependent_source_groups=dependent_groups,
            source_uris=source_uris,
            warnings=tuple(warnings),
        )
