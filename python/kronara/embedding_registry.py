from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from kronara.rag_v2 import KnowledgeChunk


@dataclass(frozen=True)
class EmbeddingModelDescriptor:
    alias: str
    provider: str
    model_id: str
    kind: Literal["embedding", "reranker"]
    dimensions: int
    max_tokens: int
    languages: tuple[str, ...]
    normalized: bool
    query_instruction: str
    license: str
    version_hash: str
    privacy: str
    health: Literal["healthy", "degraded", "unavailable", "development_only"]

    def __post_init__(self) -> None:
        if not self.alias or not self.provider or not self.model_id:
            raise ValueError("embedding identity is required")
        if self.dimensions < 8:
            raise ValueError("embedding dimensions must be at least eight")
        if self.max_tokens < 1 or not self.languages:
            raise ValueError("embedding capacity and languages are required")
        if not self.license or not self.privacy:
            raise ValueError("embedding license and privacy are required")
        if len(self.version_hash) < 8:
            raise ValueError("embedding version hash is too short")


@dataclass(frozen=True)
class EmbeddingEvaluation:
    evaluation_id: str
    model_alias: str
    golden_set_hash: str
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_precision: float
    redundancy_rate: float
    latency_ms: float
    memory_mb: float
    cases: int

    def __post_init__(self) -> None:
        quality = (
            self.recall_at_k,
            self.mrr,
            self.ndcg_at_k,
            self.citation_precision,
            self.redundancy_rate,
        )
        if any(not 0 <= value <= 1 for value in quality):
            raise ValueError("embedding quality metrics must be between zero and one")
        if self.latency_ms < 0 or self.memory_mb < 0 or self.cases < 1:
            raise ValueError("embedding resource metrics and cases must be positive")


@dataclass(frozen=True)
class EmbeddingActivationDecision:
    promoted: bool
    reason: str
    alias: str
    index_id: str | None
    ndcg_lift: float


class EmbeddingRegistry:
    def __init__(self, descriptors: tuple[EmbeddingModelDescriptor, ...]):
        self._descriptors = {item.alias: item for item in descriptors}
        if len(self._descriptors) != len(descriptors):
            raise ValueError("duplicate embedding alias")

    @classmethod
    def load(cls, path: Path) -> "EmbeddingRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported embedding registry schema")
        return cls(
            tuple(
                EmbeddingModelDescriptor(
                    alias=str(item["alias"]),
                    provider=str(item["provider"]),
                    model_id=str(item["model_id"]),
                    kind=str(item["kind"]),
                    dimensions=int(item["dimensions"]),
                    max_tokens=int(item["max_tokens"]),
                    languages=tuple(str(value) for value in item["languages"]),
                    normalized=bool(item["normalized"]),
                    query_instruction=str(item["query_instruction"]),
                    license=str(item["license"]),
                    version_hash=str(item["version_hash"]),
                    privacy=str(item["privacy"]),
                    health=str(item["health"]),
                )
                for item in payload["models"]
            )
        )

    def get(self, alias: str) -> EmbeddingModelDescriptor:
        return self._descriptors[alias]

    @property
    def aliases(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def activate(
        self,
        alias: str,
        evaluation: EmbeddingEvaluation,
        baseline: EmbeddingEvaluation,
        *,
        minimum_ndcg_lift: float = 0.02,
    ) -> EmbeddingActivationDecision:
        descriptor = self.get(alias)
        lift = evaluation.ndcg_at_k - baseline.ndcg_at_k
        reason = "material_quality_gain"
        promoted = True
        if descriptor.kind != "embedding":
            reason, promoted = "not_an_embedding_model", False
        elif descriptor.health == "development_only":
            reason, promoted = "development_only_model", False
        elif descriptor.health not in {"healthy", "degraded"}:
            reason, promoted = "model_unavailable", False
        elif evaluation.model_alias != alias:
            reason, promoted = "evaluation_alias_mismatch", False
        elif (
            evaluation.golden_set_hash != baseline.golden_set_hash
            or evaluation.cases != baseline.cases
        ):
            reason, promoted = "incomparable_evaluation_set", False
        elif lift < minimum_ndcg_lift:
            reason, promoted = "ndcg_lift_below_threshold", False
        elif evaluation.recall_at_k < baseline.recall_at_k:
            reason, promoted = "recall_regression", False
        elif evaluation.citation_precision < 0.75:
            reason, promoted = "citation_precision_below_threshold", False
        elif evaluation.redundancy_rate > 0.15:
            reason, promoted = "redundancy_above_threshold", False
        index_id = None
        if promoted:
            digest = hashlib.sha256(
                f"{descriptor.version_hash}:{evaluation.evaluation_id}".encode()
            ).hexdigest()[:16]
            index_id = f"embidx_{alias}_{digest}"
        return EmbeddingActivationDecision(promoted, reason, alias, index_id, lift)


class SentenceTransformerEmbeddingProvider:
    """Lazy local adapter; model weights are installed separately and never fetched in CI."""

    def __init__(
        self,
        descriptor: EmbeddingModelDescriptor,
        *,
        model_loader: Callable[[str], Any] | None = None,
    ):
        if descriptor.kind != "embedding":
            raise ValueError("embedding provider requires an embedding descriptor")
        self.descriptor = descriptor
        self.dimensions = descriptor.dimensions
        self._model_loader = model_loader or self._default_loader
        self._model: Any | None = None

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self.dimensions
        model = self._load()
        encoded = model.encode(
            [text],
            normalize_embeddings=self.descriptor.normalized,
            show_progress_bar=False,
        )
        first = encoded[0]
        vector = first.tolist() if hasattr(first, "tolist") else list(first)
        if len(vector) != self.dimensions:
            raise ValueError("embedding model returned incompatible dimensions")
        return [float(value) for value in vector]

    def _load(self) -> Any:
        if self._model is None:
            self._model = self._model_loader(self.descriptor.model_id)
        return self._model

    @staticmethod
    def _default_loader(model_id: str) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "sentence-transformers extra is required for real local embeddings"
            ) from error
        return SentenceTransformer(model_id)


class CrossEncoderReranker:
    def __init__(
        self,
        descriptor: EmbeddingModelDescriptor,
        *,
        model_loader: Callable[[str], Any] | None = None,
    ):
        if descriptor.kind != "reranker":
            raise ValueError("cross encoder requires a reranker descriptor")
        self.descriptor = descriptor
        self._model_loader = model_loader or self._default_loader
        self._model: Any | None = None

    def score(self, query: str, chunk: "KnowledgeChunk") -> float:
        if self._model is None:
            self._model = self._model_loader(self.descriptor.model_id)
        scores = self._model.predict([(query, chunk.content)])
        return float(scores[0])

    @staticmethod
    def _default_loader(model_id: str) -> Any:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as error:
            raise RuntimeError(
                "sentence-transformers extra is required for the local reranker"
            ) from error
        return CrossEncoder(model_id)
