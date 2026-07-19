from datetime import UTC, datetime, timedelta

from kronara.observable_tools import ObservableToolRegistry, ToolExecutionContext
from kronara.store import KronaraStore
from kronara.tools import ToolRegistry, ToolSpec


class TickingClock:
    def __init__(self):
        self.current = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

    def __call__(self):
        value = self.current
        self.current += timedelta(milliseconds=25)
        return value


def context(**overrides):
    values = {
        "run_id": "run_1",
        "agent_id": "opportunity_intelligence",
        "allowed_tools": ("reddit.list_signals",),
        "cost_budget_usd": 0.5,
    }
    values.update(overrides)
    return ToolExecutionContext(**values)


def test_invocation_persists_visible_redacted_timeline(tmp_path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    registry = ObservableToolRegistry(
        ToolRegistry(
            [
                ToolSpec(
                    "reddit.list_signals",
                    lambda _: {"count": 7, "evidence": ["ev_1"]},
                    estimated_cost_usd=0.01,
                )
            ]
        ),
        store=store,
        clock=TickingClock(),
        id_factory=lambda: "tte_1",
        summarizers={"reddit.list_signals": lambda value: f"{value['count']} señales"},
    )

    result = registry.invoke(
        context(),
        "reddit.list_signals",
        {"subreddit": "Historias", "token": "secret"},
    )
    events = store.list_tool_traces("run_1")

    assert result.ok
    assert [event.status for event in events] == ["started", "completed"]
    assert events[0].arguments_redacted["token"] == "[REDACTED]"
    assert events[-1].result_summary == "7 señales"
    assert events[-1].evidence_refs == ("ev_1",)
    assert events[-1].cost_usd == 0.01
    store.close()


def test_failure_and_circuit_open_are_visible(tmp_path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()

    def fail(_):
        raise RuntimeError("provider leaked detail")

    registry = ObservableToolRegistry(
        ToolRegistry(
            [ToolSpec("reddit.list_signals", fail)],
            failure_threshold=3,
            cooldown_seconds=60,
        ),
        store=store,
        clock=TickingClock(),
    )

    results = [registry.invoke(context(), "reddit.list_signals", {}) for _ in range(4)]
    completed_events = [
        item for item in store.list_tool_traces("run_1") if item.status != "started"
    ]

    assert results[2].error_code == "TOOL_FAILED"
    assert results[3].error_code == "TOOL_CIRCUIT_OPEN"
    assert completed_events[-1].status == "blocked"
    assert "provider leaked detail" not in completed_events[-2].result_summary
    store.close()


def test_cost_budget_blocks_before_handler_and_records_policy(tmp_path):
    calls = 0

    def handler(_):
        nonlocal calls
        calls += 1
        return {"ok": True}

    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    registry = ObservableToolRegistry(
        ToolRegistry(
            [ToolSpec("reddit.list_signals", handler, estimated_cost_usd=0.2)]
        ),
        store=store,
        clock=TickingClock(),
    )

    result = registry.invoke(
        context(cost_budget_usd=0.1), "reddit.list_signals", {}
    )
    final = store.list_tool_traces("run_1")[-1]

    assert not result.ok
    assert result.error_code == "TOOL_COST_BUDGET_EXCEEDED"
    assert calls == 0
    assert final.status == "blocked"
    assert final.policy_findings == ("TOOL_COST_BUDGET_EXCEEDED",)
    store.close()

