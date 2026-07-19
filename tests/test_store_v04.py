from datetime import UTC, datetime

from kronara.operations_contracts import MemoryRecord, ToolTraceEvent
from kronara.store import KronaraStore


def trace_event() -> ToolTraceEvent:
    started = ToolTraceEvent.started(
        event_id="tte_1",
        run_id="run_1",
        agent_id="operations_chat",
        tool_id="operations.status",
        arguments={"scope": "active"},
        started_at=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
    )
    return started.finish(
        status="completed",
        finished_at=datetime(2026, 7, 19, 12, 0, 0, 100000, tzinfo=UTC),
        result_summary="1 trabajo activo",
        evidence_refs=("ev_1",),
        artifact_refs=(),
        cost_usd=0.0,
    )


def memory_record() -> MemoryRecord:
    return MemoryRecord(
        record_id="mem_1",
        kind="episodic",
        scope="episode:ep_1",
        content="El concepto fue bloqueado por similitud.",
        provenance_uri="kronara://run/run_1",
        confidence=1.0,
        rights_mode="owned_original",
        valid_from=1,
        valid_until=None,
        version=1,
        evidence_refs=("ev_1",),
        status="supported",
    )


def test_v04_migrations_are_idempotent_and_replay_tool_traces(tmp_path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    store.initialize()
    store.save_tool_trace(trace_event())

    assert store.list_tool_traces("run_1") == [trace_event()]
    store.close()


def test_store_persists_scoped_memory_and_conversation_without_secret_fields(tmp_path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    store.save_memory(memory_record())
    store.save_conversation_turn(
        conversation_id="conv_1",
        role="user",
        content="¿Por qué se bloqueó?",
        created_at=datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
    )

    assert store.search_memory("episode:ep_1") == [memory_record()]
    assert store.list_conversation_turns("conv_1") == [
        {
            "role": "user",
            "content": "¿Por qué se bloqueó?",
            "created_at": "2026-07-19T12:00:00+00:00",
        }
    ]
    store.close()

