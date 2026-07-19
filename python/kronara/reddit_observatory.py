from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


@dataclass(frozen=True)
class ObservableRedditSignal:
    source_id: str
    source_uri: str
    theme_hint: str
    score: int
    comments: int
    age_hours: float
    language: str
    self_post: bool
    nsfw: bool
    author_deleted: bool
    post_deleted: bool
    crosspost: bool
    repost: bool
    observed_length: int
    velocity: float
    acceleration: float
    saturation: float
    lifetime_hours: float
    rights_mode: str = "reference_only"


@dataclass(frozen=True)
class RedditSignalFilters:
    min_score: int = 0
    max_score: int = 2_147_483_647
    min_comments: int = 0
    max_comments: int = 2_147_483_647
    min_age_hours: float = 0.0
    max_age_hours: float = 24 * 365.0
    language: str | None = None
    self_posts_only: bool = False
    include_nsfw: bool = False
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    min_length: int = 0
    max_length: int = 1_000_000
    allow_deleted: bool = False
    allow_crossposts: bool = False
    allow_reposts: bool = False
    min_velocity: float = 0.0
    min_acceleration: float = float("-inf")
    max_saturation: float = 1.0
    min_lifetime_hours: float = 0.0
    semantic_dedup_threshold: float = 0.92

    def __post_init__(self) -> None:
        ranges = (
            (self.min_score, self.max_score, "score"),
            (self.min_comments, self.max_comments, "comments"),
            (self.min_age_hours, self.max_age_hours, "age"),
            (self.min_length, self.max_length, "length"),
        )
        for minimum, maximum, name in ranges:
            if minimum > maximum:
                raise ValueError(f"invalid {name} range")
        if not 0 <= self.max_saturation <= 1:
            raise ValueError("maximum saturation must be between zero and one")
        if not 0 <= self.semantic_dedup_threshold <= 1:
            raise ValueError("semantic dedup threshold must be between zero and one")


@dataclass(frozen=True)
class FilteredSignals:
    signals: tuple[ObservableRedditSignal, ...]
    rejected_by_reason: dict[str, int]
    observed_count: int


class RedditObservatory:
    """Filters abstract Reddit signals; source bodies are not part of the contract."""

    def filter(
        self,
        signals: Iterable[ObservableRedditSignal],
        filters: RedditSignalFilters,
    ) -> FilteredSignals:
        source = tuple(signals)
        accepted: list[ObservableRedditSignal] = []
        reasons: Counter[str] = Counter()
        seen_ids: set[str] = set()
        seen_uris: set[str] = set()
        for signal in source:
            reason = self._rejection_reason(signal, filters)
            if reason is None and self._duplicate(signal, accepted, seen_ids, seen_uris, filters):
                reason = "duplicate"
            if reason is not None:
                reasons[reason] += 1
                continue
            accepted.append(signal)
            seen_ids.add(signal.source_id)
            seen_uris.add(signal.source_uri.casefold())
        return FilteredSignals(tuple(accepted), dict(reasons), len(source))

    @staticmethod
    def _rejection_reason(
        signal: ObservableRedditSignal,
        filters: RedditSignalFilters,
    ) -> str | None:
        normalized = signal.theme_hint.casefold()
        if not filters.min_score <= signal.score <= filters.max_score:
            return "score"
        if not filters.min_comments <= signal.comments <= filters.max_comments:
            return "comments"
        if not filters.min_age_hours <= signal.age_hours <= filters.max_age_hours:
            return "age"
        if filters.language is not None and signal.language.casefold() != filters.language.casefold():
            return "language"
        if filters.self_posts_only and not signal.self_post:
            return "not_self_post"
        if signal.nsfw and not filters.include_nsfw:
            return "nsfw"
        if filters.include_keywords and not any(
            keyword.casefold() in normalized for keyword in filters.include_keywords
        ):
            return "missing_keyword"
        if any(keyword.casefold() in normalized for keyword in filters.exclude_keywords):
            return "excluded_keyword"
        if not filters.min_length <= signal.observed_length <= filters.max_length:
            return "length"
        if (signal.author_deleted or signal.post_deleted) and not filters.allow_deleted:
            return "deleted"
        if signal.crosspost and not filters.allow_crossposts:
            return "crosspost"
        if signal.repost and not filters.allow_reposts:
            return "repost"
        if signal.velocity < filters.min_velocity:
            return "velocity"
        if signal.acceleration < filters.min_acceleration:
            return "acceleration"
        if signal.saturation > filters.max_saturation:
            return "saturation"
        if signal.lifetime_hours < filters.min_lifetime_hours:
            return "lifetime"
        return None

    @staticmethod
    def _duplicate(
        signal: ObservableRedditSignal,
        accepted: list[ObservableRedditSignal],
        seen_ids: set[str],
        seen_uris: set[str],
        filters: RedditSignalFilters,
    ) -> bool:
        if signal.source_id in seen_ids or signal.source_uri.casefold() in seen_uris:
            return True
        normalized = " ".join(signal.theme_hint.casefold().split())
        return any(
            SequenceMatcher(
                None,
                normalized,
                " ".join(item.theme_hint.casefold().split()),
            ).ratio()
            >= filters.semantic_dedup_threshold
            for item in accepted
        )

