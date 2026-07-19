from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


ResearchIntent = Literal["factual", "comparative", "causal", "exploratory", "metric", "editorial"]
ResearchRisk = Literal["low", "medium", "high"]
ClaimKind = Literal["fact", "calculation", "inference", "hypothesis", "recommendation"]
EvidenceStance = Literal["support", "oppose"]


@dataclass(frozen=True)
class ResearchQuestion:
    question_id: str
    question: str
    language: str
    max_cost_usd: float
    max_sources: int = 12
    sensitive: bool = False

    def __post_init__(self) -> None:
        if not self.question_id.strip():
            raise ValueError("question_id is required")
        if len(self.question.strip()) < 5:
            raise ValueError("question must contain at least five characters")
        if self.max_cost_usd < 0:
            raise ValueError("max_cost_usd cannot be negative")
        if self.max_sources < 2:
            raise ValueError("max_sources must be at least two")


@dataclass(frozen=True)
class SubQuestion:
    subquestion_id: str
    question: str
    focus: str
    source_budget: int
    minimum_independent_sources: int


@dataclass(frozen=True)
class SourceQuery:
    subquestion_id: str
    source_types: tuple[str, ...]
    max_results: int


@dataclass(frozen=True)
class StoppingRule:
    minimum_coverage: float
    minimum_independent_sources: int
    maximum_cost_usd: float
    maximum_queries: int
    stop_on_unresolved_high_risk_contradiction: bool = True


@dataclass(frozen=True)
class ResearchPlan:
    schema_version: int
    question_id: str
    intent: ResearchIntent
    risk: ResearchRisk
    subquestions: tuple[SubQuestion, ...]
    queries: tuple[SourceQuery, ...]
    stopping_rule: StoppingRule


@dataclass(frozen=True)
class SourceAssertion:
    claim_id: str
    subquestion_id: str
    text: str
    kind: ClaimKind
    stance: EvidenceStance
    confidence: float

    def __post_init__(self) -> None:
        if not self.claim_id.strip() or not self.subquestion_id.strip() or not self.text.strip():
            raise ValueError("claim identity, subquestion and text are required")
        if self.kind not in {"fact", "calculation", "inference", "hypothesis", "recommendation"}:
            raise ValueError("unsupported claim kind")
        if self.stance not in {"support", "oppose"}:
            raise ValueError("unsupported evidence stance")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")


@dataclass(frozen=True)
class SourceRecord:
    record_id: str
    source_uri: str
    publisher: str
    source_family: str
    published_at: datetime
    retrieved_at: datetime
    valid_until: datetime | None
    rights_mode: str
    assertions: tuple[SourceAssertion, ...]
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    subquestion_id: str
    text: str
    kind: ClaimKind
    status: Literal["supported", "weak", "contested", "opposed"]
    supporting_source_ids: tuple[str, ...]
    opposing_source_ids: tuple[str, ...]
    independent_source_count: int
    confidence: float


@dataclass(frozen=True)
class Contradiction:
    claim_id: str
    supporting_source_ids: tuple[str, ...]
    opposing_source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ResearchCoverage:
    ratio: float
    complete: bool
    covered_subquestion_ids: tuple[str, ...]
    missing_subquestion_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceMatrix:
    schema_version: int
    claims: tuple[EvidenceClaim, ...]
    contradictions: tuple[Contradiction, ...]
    coverage: ResearchCoverage
    dependent_source_groups: tuple[tuple[str, ...], ...]
    source_uris: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalyticalBrief:
    schema_version: int
    brief_id: str
    status: Literal["complete", "partial", "blocked"]
    facts: tuple[str, ...]
    calculations: tuple[str, ...]
    inferences: tuple[str, ...]
    hypotheses: tuple[str, ...]
    recommendations: tuple[str, ...]
    citations: tuple[str, ...]
    confidence: float
    coverage: ResearchCoverage
    contradictions: tuple[Contradiction, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
