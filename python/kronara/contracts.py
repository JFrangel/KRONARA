from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AutonomyMode(StrEnum):
    MANUAL = "manual"
    SUPERVISED_AUTO = "supervised_auto"
    FULL_AUTO = "full_auto"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AutonomyPolicy:
    mode: AutonomyMode = AutonomyMode.FULL_AUTO
    paused: bool = False
    daily_publication_limit: int = 3
    max_daily_cost_usd: float = 5.0
    prohibited_topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskDecision:
    level: RiskLevel
    codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    requires_human: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_uri: str
    supports: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class AgentResult:
    status: str
    state: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

