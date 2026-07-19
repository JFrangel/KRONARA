from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RankedItem:
    item_id: str
    score: float


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], constant: int = 60
) -> list[RankedItem]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (constant + rank)
    return [
        RankedItem(item_id, score)
        for item_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]


@dataclass(frozen=True)
class ModelProfile:
    alias: str
    capabilities: tuple[str, ...]
    quality: float
    cost: float
    healthy: bool
    provider: str = "configurable"


@dataclass(frozen=True)
class Candidate:
    capability: str
    max_cost: float


class ModelCapabilityRegistry:
    def __init__(self, profiles: Iterable[ModelProfile]):
        self.profiles = tuple(profiles)

    def select(self, candidate: Candidate) -> ModelProfile:
        eligible = [
            profile
            for profile in self.profiles
            if profile.healthy
            and candidate.capability in profile.capabilities
            and profile.cost <= candidate.max_cost
        ]
        if not eligible:
            raise LookupError(f"no healthy model for {candidate.capability}")
        return max(eligible, key=lambda profile: (profile.quality, -profile.cost))


DEFAULT_MODELS = (
    ModelProfile("qwen-planner", ("planning", "tools", "structured"), 0.90, 0.30, True, "router"),
    ModelProfile("kimi-researcher", ("research", "critique", "long_context"), 0.92, 0.45, True, "router"),
    ModelProfile("groq-fast", ("classification", "structured"), 0.78, 0.08, True, "groq"),
)

