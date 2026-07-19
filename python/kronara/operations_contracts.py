from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal


_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "password",
        "secret",
        "token",
    }
)


def redact_sensitive(value: Any) -> Any:
    """Return a JSON-safe shape with credential-like values removed."""
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).casefold() in _SENSITIVE_KEYS
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


@dataclass(frozen=True)
class ToolTraceEvent:
    schema_version: int
    event_id: str
    run_id: str
    agent_id: str
    tool_id: str
    status: Literal["started", "completed", "failed", "blocked"]
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    arguments_redacted: dict[str, Any]
    result_summary: str | None
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    cost_usd: float
    retry: int
    fallback: str | None
    policy_findings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported tool trace schema")
        if not all((self.event_id, self.run_id, self.agent_id, self.tool_id)):
            raise ValueError("tool trace identifiers are required")
        if self.cost_usd < 0 or self.retry < 0:
            raise ValueError("tool trace cost and retry cannot be negative")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration cannot be negative")
        for key in self.arguments_redacted:
            if key.casefold() in _SENSITIVE_KEYS and self.arguments_redacted[key] != "[REDACTED]":
                raise ValueError("sensitive argument cannot be persisted")

    @classmethod
    def started(
        cls,
        *,
        event_id: str,
        run_id: str,
        agent_id: str,
        tool_id: str,
        arguments: dict[str, Any],
        started_at: datetime,
        retry: int = 0,
        fallback: str | None = None,
    ) -> "ToolTraceEvent":
        return cls(
            schema_version=1,
            event_id=event_id,
            run_id=run_id,
            agent_id=agent_id,
            tool_id=tool_id,
            status="started",
            started_at=started_at,
            finished_at=None,
            duration_ms=None,
            arguments_redacted=redact_sensitive(arguments),
            result_summary=None,
            evidence_refs=(),
            artifact_refs=(),
            cost_usd=0.0,
            retry=retry,
            fallback=fallback,
            policy_findings=(),
        )

    def finish(
        self,
        *,
        status: Literal["completed", "failed", "blocked"],
        finished_at: datetime,
        result_summary: str,
        evidence_refs: tuple[str, ...] = (),
        artifact_refs: tuple[str, ...] = (),
        cost_usd: float = 0.0,
        policy_findings: tuple[str, ...] = (),
    ) -> "ToolTraceEvent":
        milliseconds = max(0, round((finished_at - self.started_at).total_seconds() * 1000))
        return replace(
            self,
            status=status,
            finished_at=finished_at,
            duration_ms=milliseconds,
            result_summary=result_summary,
            evidence_refs=tuple(evidence_refs),
            artifact_refs=tuple(artifact_refs),
            cost_usd=cost_usd,
            policy_findings=tuple(policy_findings),
        )


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    kind: Literal["execution", "episodic", "semantic", "performance", "conversation", "error"]
    scope: str
    content: str
    provenance_uri: str
    confidence: float
    rights_mode: str
    valid_from: int
    valid_until: int | None
    version: int
    evidence_refs: tuple[str, ...]
    status: str
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported memory schema")
        if not self.record_id or not self.scope or not self.content:
            raise ValueError("memory identity, scope and content are required")
        if not self.provenance_uri:
            raise ValueError("memory provenance is required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("memory confidence must be between zero and one")
        if not self.rights_mode:
            raise ValueError("memory rights mode is required")
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("memory validity window is invalid")
        if self.version < 1:
            raise ValueError("memory version must be positive")
        if not self.evidence_refs:
            raise ValueError("memory evidence is required")


@dataclass(frozen=True)
class OperationsContextPacket:
    schema_version: int
    packet_id: str
    run_ids: tuple[str, ...]
    workflow_snapshot: dict[str, Any]
    tool_trace_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    citations: tuple[str, ...]
    memory_record_ids: tuple[str, ...]
    provider_status: dict[str, str]
    budget_status: dict[str, float]
    coverage: float
    missing_topics: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported operations context schema")
        if not self.packet_id:
            raise ValueError("context packet id is required")
        if not 0 <= self.coverage <= 1:
            raise ValueError("context coverage must be between zero and one")


@dataclass(frozen=True)
class ActionIntent:
    schema_version: int
    intent_id: str
    kind: str
    arguments: dict[str, Any]
    risk_level: str
    status: Literal["proposed", "requires_approval", "authorized", "denied"]
    idempotency_key: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported action intent schema")
        if not self.intent_id or not self.kind or not self.idempotency_key:
            raise ValueError("action intent identifiers are required")
        redacted = redact_sensitive(self.arguments)
        if redacted != self.arguments:
            raise ValueError("action intent cannot contain credentials")


@dataclass(frozen=True)
class OperationsChatRequest:
    schema_version: int
    request_id: str
    conversation_id: str
    message: str
    minimum_context_coverage: float = 0.7

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported operations chat request schema")
        if not self.request_id or not self.conversation_id or not self.message.strip():
            raise ValueError("chat request fields are required")
        if not 0 <= self.minimum_context_coverage <= 1:
            raise ValueError("minimum context coverage must be between zero and one")


@dataclass(frozen=True)
class OperationsChatResponse:
    schema_version: int
    request_id: str
    status: Literal["completed", "partial", "blocked"]
    answer: str
    citations: tuple[str, ...]
    tool_trace_ids: tuple[str, ...]
    gaps: tuple[str, ...]
    action_intent: ActionIntent | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported operations chat response schema")
        if not self.request_id or not self.answer.strip():
            raise ValueError("chat response fields are required")

