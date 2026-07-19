from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, Literal


FEATURE_NAMES = (
    "completion_rate",
    "share_rate",
    "replay_rate",
    "velocity_signal",
    "acceleration_signal",
    "saturation_headroom",
    "freshness",
    "duration_fit",
)


@dataclass(frozen=True)
class PlatformFeatureVector:
    schema_version: int
    vector_id: str
    content_id: str
    platform: str
    observed_at: datetime
    age_hours: float
    completion_rate: float
    share_rate: float
    replay_rate: float
    velocity_per_hour: float
    acceleration_per_hour2: float
    saturation_index: float
    duration_seconds: float

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported platform feature schema")
        if any(not value.strip() for value in (self.vector_id, self.content_id, self.platform)):
            raise ValueError("feature vector identifiers are required")
        for name, value in (
            ("completion_rate", self.completion_rate),
            ("share_rate", self.share_rate),
            ("replay_rate", self.replay_rate),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between zero and one")
        if not math.isfinite(self.saturation_index) or not 0 <= self.saturation_index <= 1:
            raise ValueError("saturation_index must be between zero and one")
        if self.age_hours < 0 or self.velocity_per_hour < 0 or self.duration_seconds <= 0:
            raise ValueError("age, velocity and duration must be valid")
        if not all(
            math.isfinite(value)
            for value in (
                self.age_hours,
                self.velocity_per_hour,
                self.acceleration_per_hour2,
                self.duration_seconds,
            )
        ):
            raise ValueError("feature values must be finite")


@dataclass(frozen=True)
class PlatformObservation:
    observation_id: str
    features: PlatformFeatureVector
    outcome_viral: int
    finalized_at: datetime

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if self.outcome_viral not in {0, 1}:
            raise ValueError("outcome_viral must be binary")
        if self.finalized_at < self.features.observed_at:
            raise ValueError("outcome cannot be finalized before feature observation")


@dataclass(frozen=True)
class FeatureWeight:
    feature: str
    weight: float


@dataclass(frozen=True)
class PlatformModel:
    platform: str
    observation_count: int
    positive_count: int
    training_end: datetime
    validation_start: datetime
    intercept: float
    weights: tuple[FeatureWeight, ...]
    brier_score: float


@dataclass(frozen=True)
class ModelVersion:
    schema_version: int
    model_version: str
    trained_at: datetime | None
    minimum_observations: int
    platform_models: tuple[PlatformModel, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ViralityForecast:
    schema_version: int
    model_version: str
    platform: str
    status: Literal["estimated", "abstained"]
    probability: float | None
    interval: tuple[float, float] | None
    reason: str | None
    unknown_factors: tuple[str, ...]
    explanation: str
    guaranteed: bool = False


class ViralityModel:
    def __init__(
        self,
        *,
        minimum_observations: int = 20,
        validation_fraction: float = 0.2,
        regularization: float = 0.05,
        iterations: int = 600,
        learning_rate: float = 0.25,
    ):
        if minimum_observations < 10:
            raise ValueError("minimum_observations must be at least ten")
        if not 0.1 <= validation_fraction <= 0.4:
            raise ValueError("validation_fraction must be between 0.1 and 0.4")
        if regularization < 0 or iterations <= 0 or learning_rate <= 0:
            raise ValueError("training parameters must be positive")
        self.minimum_observations = minimum_observations
        self.validation_fraction = validation_fraction
        self.regularization = regularization
        self.iterations = iterations
        self.learning_rate = learning_rate
        self._version: ModelVersion | None = None

    def fit(self, observations: Iterable[PlatformObservation]) -> ModelVersion:
        ordered = tuple(
            sorted(
                observations,
                key=lambda item: (
                    item.features.platform,
                    item.finalized_at,
                    item.observation_id,
                ),
            )
        )
        grouped: dict[str, list[PlatformObservation]] = defaultdict(list)
        for observation in ordered:
            grouped[observation.features.platform].append(observation)

        models: list[PlatformModel] = []
        warnings: list[str] = []
        for platform, items in sorted(grouped.items()):
            positives = sum(item.outcome_viral for item in items)
            negatives = len(items) - positives
            if len(items) < self.minimum_observations or min(positives, negatives) < 2:
                warnings.append(f"insufficient_platform_data:{platform}")
                continue
            validation_count = max(1, math.ceil(len(items) * self.validation_fraction))
            split_index = len(items) - validation_count
            training = items[:split_index]
            validation = items[split_index:]
            if len({item.outcome_viral for item in training}) < 2:
                warnings.append(f"insufficient_training_classes:{platform}")
                continue
            intercept, weights = self._train(training)
            brier = sum(
                (self._probability(intercept, weights, item.features) - item.outcome_viral) ** 2
                for item in validation
            ) / len(validation)
            models.append(
                PlatformModel(
                    platform=platform,
                    observation_count=len(items),
                    positive_count=positives,
                    training_end=training[-1].finalized_at,
                    validation_start=validation[0].finalized_at,
                    intercept=intercept,
                    weights=tuple(
                        FeatureWeight(feature=name, weight=round(value, 10))
                        for name, value in zip(FEATURE_NAMES, weights)
                    ),
                    brier_score=round(brier, 10),
                )
            )

        version_id = self._version_hash(ordered)
        self._version = ModelVersion(
            schema_version=1,
            model_version=version_id,
            trained_at=max((item.finalized_at for item in ordered), default=None),
            minimum_observations=self.minimum_observations,
            platform_models=tuple(models),
            warnings=tuple(warnings),
        )
        return self._version

    def predict(self, features: PlatformFeatureVector) -> ViralityForecast:
        if self._version is None:
            raise RuntimeError("fit must be called before predict")
        platform_model = next(
            (
                item
                for item in self._version.platform_models
                if item.platform == features.platform
            ),
            None,
        )
        unknown = (
            "algorithm_change",
            "audience_shift",
            "creative_quality_not_encoded",
            "external_competition",
        )
        if platform_model is None:
            return ViralityForecast(
                schema_version=1,
                model_version=self._version.model_version,
                platform=features.platform,
                status="abstained",
                probability=None,
                interval=None,
                reason="insufficient_platform_data",
                unknown_factors=unknown,
                explanation="No hay datos suficientes de esta plataforma para estimar una probabilidad.",
            )
        raw_weights = tuple(item.weight for item in platform_model.weights)
        probability = self._probability(platform_model.intercept, raw_weights, features)
        sampling_margin = 1.96 * math.sqrt(
            probability * (1 - probability) / platform_model.observation_count
        )
        margin = min(0.45, max(0.03, sampling_margin + 0.2 * platform_model.brier_score))
        interval = (max(0.0, probability - margin), min(1.0, probability + margin))
        return ViralityForecast(
            schema_version=1,
            model_version=self._version.model_version,
            platform=features.platform,
            status="estimated",
            probability=round(probability, 6),
            interval=(round(interval[0], 6), round(interval[1], 6)),
            reason=None,
            unknown_factors=unknown,
            explanation=(
                "Probabilidad estimada desde resultados históricos separados por plataforma; "
                "no es una garantía de viralidad ni una descripción del algoritmo privado."
            ),
        )

    def _train(self, training: list[PlatformObservation]) -> tuple[float, tuple[float, ...]]:
        vectors = [self._encode(item.features) for item in training]
        outcomes = [float(item.outcome_viral) for item in training]
        mean = sum(outcomes) / len(outcomes)
        intercept = math.log(mean / (1 - mean))
        weights = [0.0] * len(FEATURE_NAMES)
        for _ in range(self.iterations):
            intercept_gradient = 0.0
            gradients = [0.0] * len(weights)
            for vector, outcome in zip(vectors, outcomes):
                prediction = self._sigmoid(
                    intercept + sum(weight * value for weight, value in zip(weights, vector))
                )
                error = prediction - outcome
                intercept_gradient += error
                for index, value in enumerate(vector):
                    gradients[index] += error * value
            count = len(training)
            intercept -= self.learning_rate * intercept_gradient / count
            for index in range(len(weights)):
                gradient = gradients[index] / count + self.regularization * weights[index]
                weights[index] -= self.learning_rate * gradient
        return round(intercept, 10), tuple(round(value, 10) for value in weights)

    @classmethod
    def _probability(
        cls,
        intercept: float,
        weights: tuple[float, ...],
        features: PlatformFeatureVector,
    ) -> float:
        vector = cls._encode(features)
        return cls._sigmoid(intercept + sum(weight * value for weight, value in zip(weights, vector)))

    @staticmethod
    def _encode(features: PlatformFeatureVector) -> tuple[float, ...]:
        return (
            features.completion_rate,
            features.share_rate,
            features.replay_rate,
            min(1.0, math.log1p(features.velocity_per_hour) / math.log1p(1000)),
            math.tanh(features.acceleration_per_hour2 / 25),
            1 - features.saturation_index,
            math.exp(-features.age_hours / 72),
            math.exp(-abs(features.duration_seconds - 45) / 45),
        )

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            return 1 / (1 + math.exp(-value))
        exponential = math.exp(value)
        return exponential / (1 + exponential)

    @staticmethod
    def _version_hash(observations: tuple[PlatformObservation, ...]) -> str:
        payload = []
        for observation in observations:
            item = asdict(observation)
            item["features"]["observed_at"] = observation.features.observed_at.isoformat()
            item["finalized_at"] = observation.finalized_at.isoformat()
            payload.append(item)
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
