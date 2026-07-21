from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    handler: Callable[[dict[str, Any]], Any]
    side_effect: bool = False
    # A real story-generation tool (story.concept/blueprint/draft) can chain
    # several sequential OpenRouter calls before succeeding -- a "creative_
    # primary" alias alone has 5 fallback candidates, and free-tier models
    # are frequently slower than paid ones under load. 30s was tuned for
    # deterministic/local tools; the first genuinely end-to-end real run
    # (real Reddit, real OpenRouter, real fallback chain) measured a single
    # story-generation step legitimately exceeding it. 120s is generous for
    # every real call observed so far while still catching an actually-hung
    # tool rather than waiting forever.
    timeout_seconds: float = 120.0
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("tool timeout must be positive")
        if self.estimated_cost_usd < 0:
            raise ValueError("tool estimated cost cannot be negative")


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

    def get_spec(self, tool_id: str) -> ToolSpec | None:
        return self._tools.get(tool_id)

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
            elapsed = self.clock() - started_at
            if elapsed > tool.timeout_seconds:
                self._record_failure(tool_id)
                print(
                    f"[tool_timeout] tool_id={tool_id} agent_id={agent_id} "
                    f"elapsed={elapsed:.1f}s deadline={tool.timeout_seconds:.1f}s",
                    file=sys.stderr,
                )
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
            # The caller (ToolResult.message) only ever sees the exception's
            # type name -- never its text, which could carry provider
            # internals. But that means a real failure was previously
            # undiagnosable by anyone, including whoever runs Kronara
            # locally. stderr now lands in a real log file (see rpc.py /
            # SidecarProcess::spawn in sidecar_bridge.rs).
            print(f"[tool_failed] tool_id={tool_id} agent_id={agent_id}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
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
