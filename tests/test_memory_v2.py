from kronara.memory_v2 import MemoryCandidate, MemoryCurator


def candidate(
    record_id: str,
    content: str,
    *,
    kind: str = "semantic",
    rights_mode: str = "owned_original",
    valid_until: int | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        record_id=record_id,
        kind=kind,
        scope="editorial:voice",
        content=content,
        provenance_uri=f"kronara://experiment/{record_id}",
        confidence=0.7,
        rights_mode=rights_mode,
        valid_from=100,
        valid_until=valid_until,
        version=1,
        evidence_refs=(f"ev_{record_id}",),
        proposed_status="hypothesis",
    )


def test_contradictory_memories_coexist_as_competing_hypotheses():
    curator = MemoryCurator(now=lambda: 150)
    left = curator.propose(candidate("mem_a", "La voz A mejora retención"))
    right = curator.propose(candidate("mem_b", "La voz A reduce retención"))

    assert left.record.record_id != right.record.record_id
    assert {left.status, right.status} == {"hypothesis"}
    assert left.reason == right.reason == "stored_as_competing_hypothesis"


def test_external_story_body_is_rejected_from_durable_memory():
    decision = MemoryCurator(now=lambda: 150).propose(
        candidate("mem_external", "Texto completo externo", rights_mode="reference_only")
    )

    assert decision.status == "rejected"
    assert decision.reason == "rights_not_reusable"
    assert decision.record is None


def test_expired_memory_and_unsupported_status_fail_closed():
    expired = MemoryCurator(now=lambda: 200).propose(
        candidate("mem_expired", "Aprendizaje viejo", valid_until=199)
    )
    unsupported = MemoryCurator(now=lambda: 150).propose(
        MemoryCandidate(
            **{
                **candidate("mem_policy", "Cambiar política").__dict__,
                "proposed_status": "global_policy",
            }
        )
    )

    assert expired.reason == "memory_expired"
    assert unsupported.reason == "unsupported_memory_status"

