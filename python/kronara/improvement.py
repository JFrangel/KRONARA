from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Callable, Iterable, Literal

from kronara.store import KronaraStore
from kronara.training_rights import TrainingAsset, TrainingRightsPolicy


AUTOMATIC_PARAMETERS = {
    "voice_id",
    "duration_seconds",
    "publication_hour",
    "hook_id",
    "packaging_variant",
    "rag_ranking",
    "query_expansion",
    "model_alias",
}
SUPERVISED_PARAMETERS = {"system_prompt", "skill_catalog", "embedding_model"}
ADMINISTRATIVE_PARAMETERS = {
    "rights_policy",
    "autonomy_policy",
    "max_budget",
    "editorial_identity",
    "source_authorization",
    "fine_tuning_deployment",
}


@dataclass(frozen=True)
class EvaluationSet:
    set_id: str
    version: int
    frozen: bool
    content_hash: str
    case_count: int

    def __post_init__(self) -> None:
        if not self.set_id.strip() or not self.content_hash.strip():
            raise ValueError("evaluation set identity is required")
        if self.version <= 0 or self.case_count <= 0:
            raise ValueError("evaluation set version and cases must be positive")


@dataclass(frozen=True)
class CandidateVersion:
    version_id: str
    parameter: str
    config_hash: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.version_id, self.parameter, self.config_hash)):
            raise ValueError("candidate identity, parameter and hash are required")
        if self.expires_at <= self.created_at:
            raise ValueError("candidate expiry must follow creation")


@dataclass(frozen=True)
class CandidateEvaluation:
    evaluation_id: str
    evaluation_set: EvaluationSet
    sample_size: int
    champion_score: float
    challenger_score: float
    safety_regressions: tuple[str, ...]
    cost_change_ratio: float
    platform_stability: float

    def __post_init__(self) -> None:
        if not self.evaluation_id.strip() or self.sample_size < 0:
            raise ValueError("evaluation identity and sample are required")
        if not 0 <= self.champion_score <= 1 or not 0 <= self.challenger_score <= 1:
            raise ValueError("evaluation scores must be between zero and one")
        if self.cost_change_ratio < -1:
            raise ValueError("cost change ratio is invalid")
        if not 0 <= self.platform_stability <= 1:
            raise ValueError("platform stability must be between zero and one")


@dataclass(frozen=True)
class DeploymentDecision:
    schema_version: int
    decision_id: str
    status: Literal["promoted", "rejected", "testing", "requires_approval"]
    champion_version: str
    challenger_version: str
    parameter: str
    authority_required: Literal["automatic", "supervised", "administrative"]
    relative_lift: float
    reason: str
    evaluation_set_id: str
    evaluation_set_hash: str
    reversible: bool


@dataclass(frozen=True)
class RollbackReceipt:
    schema_version: int
    version_id: str
    status: Literal["rolled_back"]
    restored_version: str
    reason: str


@dataclass(frozen=True)
class ErrorMemory:
    error_id: str
    taxonomy: str
    task_type: str
    signature: str
    evidence_uri: str
    occurred_at: datetime
    resolved_by_version: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.error_id,
            self.taxonomy,
            self.task_type,
            self.signature,
            self.evidence_uri,
        )
        if any(not value.strip() for value in required):
            raise ValueError("error memory fields are required")


@dataclass(frozen=True)
class LearningHypothesis:
    hypothesis_id: str
    statement: str
    state: Literal["hypothesis", "testing", "supported", "promoted", "rejected", "expired"]
    evidence_ids: tuple[str, ...]
    rival_ids: tuple[str, ...]
    valid_until: datetime

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip() or not self.statement.strip():
            raise ValueError("hypothesis identity and statement are required")
        if self.state not in {"hypothesis", "testing", "supported", "promoted", "rejected", "expired"}:
            raise ValueError("unsupported learning state")
        if self.hypothesis_id in self.rival_ids:
            raise ValueError("hypothesis cannot rival itself")


class ImprovementEngine:
    def __init__(
        self,
        *,
        store: KronaraStore | None = None,
        minimum_sample: int = 100,
        minimum_relative_lift: float = 0.05,
        maximum_cost_increase: float = 0.15,
        minimum_platform_stability: float = 0.8,
        now: Callable[[], datetime] | None = None,
    ):
        self.store = store
        self.minimum_sample = minimum_sample
        self.minimum_relative_lift = minimum_relative_lift
        self.maximum_cost_increase = maximum_cost_increase
        self.minimum_platform_stability = minimum_platform_stability
        self.now = now or (lambda: datetime.now(UTC))
        self._decisions: dict[str, dict] = {}
        self._errors: dict[str, dict] = {}
        self._hypotheses: dict[str, dict] = {}

    def evaluate(
        self,
        champion: CandidateVersion,
        challenger: CandidateVersion,
        evaluation: CandidateEvaluation,
    ) -> DeploymentDecision:
        authority = self._authority(challenger.parameter)
        relative_lift = (
            (evaluation.challenger_score - evaluation.champion_score)
            / evaluation.champion_score
            if evaluation.champion_score > 0
            else 0.0
        )
        if not evaluation.evaluation_set.frozen:
            status, reason = "rejected", "evaluation_set_not_frozen"
        elif challenger.expires_at <= self.now():
            status, reason = "rejected", "candidate_expired"
        elif evaluation.sample_size < self.minimum_sample:
            status, reason = "testing", "insufficient_sample"
        elif evaluation.safety_regressions:
            status, reason = "rejected", "safety_regression"
        elif evaluation.cost_change_ratio > self.maximum_cost_increase:
            status, reason = "rejected", "cost_regression"
        elif evaluation.platform_stability < self.minimum_platform_stability:
            status, reason = "rejected", "unstable_across_platform_segments"
        elif relative_lift < self.minimum_relative_lift:
            status, reason = "rejected", "no_material_lift"
        elif authority != "automatic":
            status, reason = "requires_approval", f"{authority}_approval_required"
        else:
            status, reason = "promoted", "material_safe_stable_gain"

        decision = DeploymentDecision(
            schema_version=1,
            decision_id=self._decision_id(challenger, evaluation),
            status=status,
            champion_version=champion.version_id,
            challenger_version=challenger.version_id,
            parameter=challenger.parameter,
            authority_required=authority,
            relative_lift=relative_lift,
            reason=reason,
            evaluation_set_id=evaluation.evaluation_set.set_id,
            evaluation_set_hash=evaluation.evaluation_set.content_hash,
            reversible=status == "promoted",
        )
        self._persist(challenger.version_id, asdict(decision))
        return decision

    def rollback(self, version_id: str, reason: str) -> RollbackReceipt:
        if not reason.strip():
            raise ValueError("rollback reason is required")
        payload = self._load(version_id)
        if payload.get("status") != "promoted":
            raise ValueError("only promoted versions can be rolled back")
        receipt = RollbackReceipt(
            schema_version=1,
            version_id=version_id,
            status="rolled_back",
            restored_version=str(payload["champion_version"]),
            reason=reason,
        )
        updated = {**payload, "status": "rolled_back", "rollback": asdict(receipt)}
        self._persist(version_id, updated)
        return receipt

    def record_error(self, memory: ErrorMemory) -> None:
        payload = asdict(memory)
        payload["occurred_at"] = memory.occurred_at.isoformat()
        self._errors[memory.error_id] = payload
        if self.store is not None:
            self.store.save_error_memory(memory.error_id, payload)

    def resolve_error(self, error_id: str, version_id: str) -> None:
        if not version_id.strip():
            raise ValueError("resolution version is required")
        if error_id in self._errors:
            payload = self._errors[error_id]
        elif self.store is not None:
            payload = self.store.load_error_memory(error_id)
        else:
            raise KeyError(error_id)
        updated = {**payload, "resolved_by_version": version_id}
        self._errors[error_id] = updated
        if self.store is not None:
            self.store.save_error_memory(error_id, updated)

    def record_hypothesis(self, hypothesis: LearningHypothesis) -> None:
        payload = asdict(hypothesis)
        payload["valid_until"] = hypothesis.valid_until.isoformat()
        self._hypotheses[hypothesis.hypothesis_id] = payload
        if self.store is not None:
            self.store.save_learning_hypothesis(hypothesis.hypothesis_id, payload)

    def _persist(self, version_id: str, payload: dict) -> None:
        self._decisions[version_id] = payload
        if self.store is not None:
            self.store.save_improvement_decision(version_id, str(payload["status"]), payload)

    def _load(self, version_id: str) -> dict:
        if version_id in self._decisions:
            return self._decisions[version_id]
        if self.store is not None:
            return self.store.load_improvement_decision(version_id)
        raise KeyError(version_id)

    @staticmethod
    def _authority(parameter: str) -> str:
        if parameter in AUTOMATIC_PARAMETERS:
            return "automatic"
        if parameter in SUPERVISED_PARAMETERS:
            return "supervised"
        return "administrative"

    @staticmethod
    def _decision_id(
        challenger: CandidateVersion,
        evaluation: CandidateEvaluation,
    ) -> str:
        identity = (
            f"{challenger.version_id}:{challenger.config_hash}:"
            f"{evaluation.evaluation_id}:{evaluation.evaluation_set.content_hash}"
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


class DatasetRightsError(ValueError):
    pass


@dataclass(frozen=True)
class TrainingExample:
    example_id: str
    asset: TrainingAsset
    split: Literal["train", "validation", "test"]


@dataclass(frozen=True)
class DatasetCard:
    schema_version: int
    dataset_id: str
    example_count: int
    split_counts: tuple[tuple[str, int], ...]
    manifest_hash: str
    rights_evidence: tuple[str, ...]
    rights_modes: tuple[str, ...]


class DatasetCardBuilder:
    def __init__(self, policy: TrainingRightsPolicy | None = None):
        self.policy = policy or TrainingRightsPolicy()

    def build(
        self,
        dataset_id: str,
        examples: Iterable[TrainingExample],
        *,
        commercial_use: bool,
    ) -> DatasetCard:
        ordered = tuple(sorted(examples, key=lambda item: item.example_id))
        if not dataset_id.strip() or not ordered:
            raise ValueError("dataset_id and examples are required")
        if len({item.example_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate training example id")
        evidence: list[str] = []
        rights_modes: set[str] = set()
        manifest: list[dict[str, str]] = []
        counts: dict[str, int] = {}
        for example in ordered:
            if example.split not in {"train", "validation", "test"}:
                raise ValueError("unsupported dataset split")
            decision = self.policy.decide(example.asset, commercial_use=commercial_use)
            if not decision.allowed:
                raise DatasetRightsError(
                    f"training example {example.example_id} rejected: {decision.code}"
                )
            counts[example.split] = counts.get(example.split, 0) + 1
            if decision.evidence_uri:
                evidence.append(decision.evidence_uri)
            rights_modes.add(example.asset.rights_mode.value)
            manifest.append(
                {
                    "example_id": example.example_id,
                    "asset_id": example.asset.asset_id,
                    "rights_mode": example.asset.rights_mode.value,
                    "source_uri": example.asset.source_uri,
                    "split": example.split,
                }
            )
        normalized = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return DatasetCard(
            schema_version=1,
            dataset_id=dataset_id,
            example_count=len(ordered),
            split_counts=tuple(sorted(counts.items())),
            manifest_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            rights_evidence=tuple(sorted(set(evidence))),
            rights_modes=tuple(sorted(rights_modes)),
        )
