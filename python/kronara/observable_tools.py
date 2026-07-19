from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from kronara.operations_contracts import ToolTraceEvent
from kronara.store import KronaraStore
from kronara.tools import ToolRegistry, ToolResult


@dataclass(frozen=True)
class ToolExecutionContext:
    run_id: str
    agent_id: str
    allowed_tools: tuple[str, ...]
    cost_budget_usd: float

    def __post_init__(self) -> None:
        if not self.run_id or not self.agent_id:
            raise ValueError("tool execution identity is required")
        if self.cost_budget_usd < 0:
            raise ValueError("tool cost budget cannot be negative")


class ObservableToolRegistry:
    """Adds durable, redacted lifecycle events to the governed tool registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        store: KronaraStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        id_factory: Callable[[], str] = lambda: f"tte_{uuid4().hex}",
        summarizers: dict[str, Callable[[Any], str]] | None = None,
    ):
        self.registry = registry
        self.store = store
        self.clock = clock
        self.id_factory = id_factory
        self.summarizers = dict(summarizers or {})
        self._spent_by_run: dict[str, float] = {}

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return self.registry.tool_ids

    def invoke(
        self,
        context: ToolExecutionContext,
        tool_id: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        started = ToolTraceEvent.started(
            event_id=self.id_factory(),
            run_id=context.run_id,
            agent_id=context.agent_id,
            tool_id=tool_id,
            arguments=arguments,
            started_at=self.clock(),
        )
        self.store.save_tool_trace(started)
        spec = self.registry.get_spec(tool_id)
        estimated_cost = spec.estimated_cost_usd if spec is not None else 0.0
        spent = self._spent_by_run.get(context.run_id, 0.0)
        if spent + estimated_cost > context.cost_budget_usd:
            result = ToolResult(
                False,
                error_code="TOOL_COST_BUDGET_EXCEEDED",
                message="tool cost budget exceeded",
            )
        else:
            result = self.registry.invoke(
                context.agent_id,
                context.allowed_tools,
                tool_id,
                arguments,
            )
            self._spent_by_run[context.run_id] = spent + estimated_cost
        self.store.save_tool_trace(
            started.finish(
                status=self._status(result),
                finished_at=self.clock(),
                result_summary=self._summary(tool_id, result),
                evidence_refs=self._references(result.value, "evidence"),
                artifact_refs=self._references(result.value, "artifacts", singular="artifact"),
                cost_usd=estimated_cost if result.error_code != "TOOL_COST_BUDGET_EXCEEDED" else 0.0,
                policy_findings=(result.error_code,) if self._status(result) == "blocked" and result.error_code else (),
            )
        )
        return result

    @staticmethod
    def _status(result: ToolResult) -> str:
        if result.ok:
            return "completed"
        if result.error_code in {"TOOL_FAILED", "TOOL_TIMEOUT"}:
            return "failed"
        return "blocked"

    def _summary(self, tool_id: str, result: ToolResult) -> str:
        if result.ok:
            summarizer = self.summarizers.get(tool_id)
            if summarizer is not None:
                try:
                    return str(summarizer(result.value))[:2000]
                except Exception:
                    return "tool completed; summary unavailable"
            if isinstance(result.value, dict) and "count" in result.value:
                return f"tool completed with {result.value['count']} results"
            return "tool completed"
        return f"{result.error_code or 'TOOL_FAILED'}: {result.message or 'tool failed'}"[:2000]

    @staticmethod
    def _references(value: Any, plural: str, *, singular: str | None = None) -> tuple[str, ...]:
        if not isinstance(value, dict):
            return ()
        raw = value.get(plural)
        if raw is None and singular is not None and value.get(singular) is not None:
            raw = (value[singular],)
        if raw is None:
            return ()
        if not isinstance(raw, (list, tuple)):
            raw = (raw,)
        references: list[str] = []
        for item in raw:
            identifier = getattr(item, "evidence_id", None) or getattr(item, "artifact_id", None)
            references.append(str(identifier if identifier is not None else item))
        return tuple(references)

