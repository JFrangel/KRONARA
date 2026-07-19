from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Literal


HealthState = Literal["healthy", "degraded", "unavailable", "unknown"]


class NoHealthyModelError(LookupError):
    pass


@dataclass(frozen=True)
class ModelRequirements:
    required_capabilities: frozenset[str]
    minimum_context_tokens: int = 0
    structured_output: bool = False
    tool_calling: bool = False


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model_id: str
    capabilities: frozenset[str]
    context_tokens: int
    structured_output: bool
    tool_calling: bool
    expires_on: date | None
    quality_score: float
    reliability_score: float
    cost_score: float
    privacy: str
    experimental: bool = False
    dynamic_catalog: bool = False

    @property
    def score(self) -> float:
        return (
            0.45 * self.quality_score
            + 0.35 * self.reliability_score
            + 0.20 * self.cost_score
        )


@dataclass(frozen=True)
class ModelRoute:
    requested_alias: str
    primary: str
    primary_provider: str
    fallbacks: tuple[str, ...]
    selection_reasons: tuple[str, ...]


class ModelCapabilityRegistryV2:
    def __init__(
        self,
        candidates: tuple[ModelCandidate, ...],
        aliases: dict[str, tuple[str, ...]],
        *,
        now: Callable[[], date] = date.today,
    ):
        self._candidates = {candidate.model_id: candidate for candidate in candidates}
        self._aliases = aliases
        self._now = now
        if len(self._candidates) != len(candidates):
            raise ValueError("duplicate model id")
        for alias, model_ids in aliases.items():
            unknown = set(model_ids) - set(self._candidates)
            if unknown:
                raise ValueError(f"alias {alias} references unknown models: {sorted(unknown)}")

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        now: Callable[[], date] = date.today,
    ) -> "ModelCapabilityRegistryV2":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 2:
            raise ValueError("unsupported model registry schema")
        candidates = tuple(cls._candidate(item) for item in payload["candidates"])
        aliases = {
            str(alias): tuple(str(model_id) for model_id in model_ids)
            for alias, model_ids in payload["aliases"].items()
        }
        return cls(candidates, aliases, now=now)

    def resolve(
        self,
        alias: str,
        requirements: ModelRequirements,
        health: dict[str, HealthState],
    ) -> ModelRoute:
        if alias not in self._aliases:
            raise NoHealthyModelError(f"no healthy model for unknown alias {alias}")
        eligible: list[ModelCandidate] = []
        reasons: list[str] = []
        for model_id in self._aliases[alias]:
            candidate = self._candidates[model_id]
            if candidate.expires_on is not None and self._now() > candidate.expires_on:
                reasons.append(f"expired:{model_id}")
                continue
            state = health.get(model_id, "unknown")
            if state not in {"healthy", "degraded"}:
                reasons.append(f"unhealthy:{model_id}")
                continue
            if not requirements.required_capabilities <= candidate.capabilities:
                reasons.append(f"capability_mismatch:{model_id}")
                continue
            if candidate.context_tokens < requirements.minimum_context_tokens:
                reasons.append(f"context_too_small:{model_id}")
                continue
            if requirements.structured_output and not candidate.structured_output:
                reasons.append(f"structured_output_unavailable:{model_id}")
                continue
            if requirements.tool_calling and not candidate.tool_calling:
                reasons.append(f"tool_calling_unavailable:{model_id}")
                continue
            eligible.append(candidate)
        eligible.sort(
            key=lambda item: (
                self._aliases[alias].index(item.model_id),
                -item.score,
            )
        )
        if not eligible:
            raise NoHealthyModelError(f"no healthy model satisfies alias {alias}")
        primary = eligible[0]
        fallbacks = tuple(item.model_id for item in eligible[1:])
        if primary.experimental and not fallbacks:
            raise NoHealthyModelError(f"no healthy model fallback for experimental alias {alias}")
        if primary.experimental:
            reasons.append("experimental")
        if health.get(primary.model_id) == "degraded":
            reasons.append(f"degraded:{primary.model_id}")
        reasons.append(f"selected_by_alias_capability_score:{primary.model_id}")
        return ModelRoute(
            requested_alias=alias,
            primary=primary.model_id,
            primary_provider=primary.provider,
            fallbacks=fallbacks,
            selection_reasons=tuple(reasons),
        )

    def provider_for(self, model_id: str) -> str:
        try:
            return self._candidates[model_id].provider
        except KeyError as error:
            raise NoHealthyModelError(f"unknown model {model_id}") from error

    @staticmethod
    def _candidate(payload: dict) -> ModelCandidate:
        expires = payload.get("expires_on")
        return ModelCandidate(
            provider=str(payload["provider"]),
            model_id=str(payload["model_id"]),
            capabilities=frozenset(str(item) for item in payload["capabilities"]),
            context_tokens=int(payload["context_tokens"]),
            structured_output=bool(payload["structured_output"]),
            tool_calling=bool(payload["tool_calling"]),
            expires_on=date.fromisoformat(str(expires)) if expires else None,
            quality_score=float(payload["quality_score"]),
            reliability_score=float(payload["reliability_score"]),
            cost_score=float(payload["cost_score"]),
            privacy=str(payload["privacy"]),
            experimental=bool(payload.get("experimental", False)),
            dynamic_catalog=bool(payload.get("dynamic_catalog", False)),
        )
