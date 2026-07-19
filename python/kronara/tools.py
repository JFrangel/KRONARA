from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    handler: Callable[[dict[str, Any]], Any]
    side_effect: bool = False
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    value: Any = None
    error_code: str | None = None
    message: str | None = None


class ToolRegistry:
    """Governed tool dispatcher with allowlists, anti-loop and circuit breaking."""

    def __init__(
        self,
        tools: Iterable[ToolSpec],
        *,
        repeat_limit: int = 3,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._tools = {tool.tool_id: tool for tool in tools}
        self.repeat_limit = repeat_limit
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self._signatures: Counter[str] = Counter()
        self._failures: Counter[str] = Counter()
        self._opened_at: dict[str, float] = {}

    @property
    def tool_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def invoke(
        self,
        agent_id: str,
        allowed_tools: Iterable[str],
        tool_id: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        if tool_id not in set(allowed_tools):
            return ToolResult(False, error_code="TOOL_NOT_ALLOWED", message="tool denied")
        tool = self._tools.get(tool_id)
        if tool is None:
            return ToolResult(False, error_code="TOOL_UNKNOWN", message="tool is not registered")
        if self._failures[tool_id] >= self.failure_threshold:
            opened_at = self._opened_at.get(tool_id, self.clock())
            if self.clock() - opened_at < self.cooldown_seconds:
                return ToolResult(False, error_code="TOOL_CIRCUIT_OPEN", message="tool temporarily disabled")
            self._failures[tool_id] = 0
            self._opened_at.pop(tool_id, None)

        signature = self._signature(agent_id, tool_id, arguments)
        self._signatures[signature] += 1
        if self._signatures[signature] > self.repeat_limit:
            return ToolResult(False, error_code="TOOL_LOOP_DETECTED", message="repeated call stopped")

        started_at = self.clock()
        try:
            value = tool.handler(dict(arguments))
            if self.clock() - started_at > tool.timeout_seconds:
                self._record_failure(tool_id)
                return ToolResult(
                    False,
                    error_code="TOOL_TIMEOUT",
                    message="tool exceeded its deadline",
                )
            self._failures[tool_id] = 0
            self._opened_at.pop(tool_id, None)
            return ToolResult(True, value=value)
        except Exception as error:  # Tool boundaries convert provider failures to data.
            self._record_failure(tool_id)
            return ToolResult(
                False,
                error_code="TOOL_FAILED",
                message=f"{type(error).__name__}: provider call failed",
            )

    def _record_failure(self, tool_id: str) -> None:
        self._failures[tool_id] += 1
        if self._failures[tool_id] >= self.failure_threshold:
            self._opened_at[tool_id] = self.clock()

    @staticmethod
    def _signature(agent_id: str, tool_id: str, arguments: dict[str, Any]) -> str:
        serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(f"{agent_id}:{tool_id}:{serialized}".encode()).hexdigest()
