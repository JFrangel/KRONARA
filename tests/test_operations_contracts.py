from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from kronara.operations_contracts import (
    ActionIntent,
    MemoryRecord,
    OperationsChatRequest,
    OperationsChatResponse,
    OperationsContextPacket,
    ToolTraceEvent,
)


NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def test_tool_trace_redacts_secrets_and_never_exposes_private_reasoning():
    trace = ToolTraceEvent.started(
        event_id="tte_1",
        run_id="run_1",
        agent_id="operations_chat",
        tool_id="reddit.list_signals",
        arguments={
            "subreddit": "Historias",
            "client_secret": "secret",
            "nested": {"authorization": "Bearer secret", "limit": 25},
        },
        started_at=NOW,
    )

    assert trace.arguments_redacted == {
        "subreddit": "Historias",
        "client_secret": "[REDACTED]",
        "nested": {"authorization": "[REDACTED]", "limit": 25},
    }
    assert "private_reasoning" not in ToolTraceEvent.__dataclass_fields__
    serialized = str(asdict(trace))
    assert "Bearer secret" not in serialized
    assert "'secret'" not in serialized


def test_tool_trace_completion_preserves_identity_and_safe_summary():
    started = ToolTraceEvent.started(
        event_id="tte_1",
        run_id="run_1",
        agent_id="operations_chat",
        tool_id="operations.status",
        arguments={},
        started_at=NOW,
    )

    completed = started.finish(
        status="completed",
        finished_at=datetime(2026, 7, 19, 12, 0, 0, 250000, tzinfo=UTC),
        result_summary="2 agentes activos",
        evidence_refs=("ev_1",),
        artifact_refs=(),
        cost_usd=0.001,
    )

    assert completed.event_id == started.event_id
    assert completed.duration_ms == 250
    assert completed.evidence_refs == ("ev_1",)


def test_memory_requires_provenance_rights_evidence_and_bounded_confidence():
    with pytest.raises(ValueError, match="provenance"):
        MemoryRecord(
            record_id="mem_1",
            kind="semantic",
            scope="editorial",
            content="Regla",
            provenance_uri="",
            confidence=0.9,
            rights_mode="owned_original",
            valid_from=1,
            valid_until=None,
            version=1,
            evidence_refs=("ev_1",),
            status="supported",
        )

    with pytest.raises(ValueError, match="confidence"):
        MemoryRecord(
            record_id="mem_2",
            kind="semantic",
            scope="editorial",
            content="Regla",
            provenance_uri="kronara://artifact/a",
            confidence=1.1,
            rights_mode="owned_original",
            valid_from=1,
            valid_until=None,
            version=1,
            evidence_refs=("ev_1",),
            status="supported",
        )


def test_chat_contract_distinguishes_read_answer_from_governed_intent():
    request = OperationsChatRequest(
        schema_version=1,
        request_id="req_1",
        conversation_id="conv_1",
        message="¿Qué está bloqueado?",
        minimum_context_coverage=0.75,
    )
    packet = OperationsContextPacket(
        schema_version=1,
        packet_id="ctx_1",
        run_ids=("run_1",),
        workflow_snapshot={"blocked": 1},
        tool_trace_ids=("tte_1",),
        evidence_refs=("ev_1",),
        citations=("kronara://evidence/ev_1",),
        memory_record_ids=(),
        provider_status={"planning_primary": "healthy"},
        budget_status={"remaining_usd": 4.0},
        coverage=1.0,
        missing_topics=(),
    )
    intent = ActionIntent(
        schema_version=1,
        intent_id="intent_1",
        kind="set_budget",
        arguments={"maximum_usd": 10.0},
        risk_level="administrative",
        status="requires_approval",
        idempotency_key="conv_1:set_budget:10",
    )
    response = OperationsChatResponse(
        schema_version=1,
        request_id=request.request_id,
        status="completed",
        answer="Hay un trabajo bloqueado por derechos.",
        citations=packet.citations,
        tool_trace_ids=packet.tool_trace_ids,
        gaps=(),
        action_intent=intent,
    )

    assert response.action_intent.status == "requires_approval"
    assert response.citations == ("kronara://evidence/ev_1",)
