from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourcePost:
    source_id: str
    title: str
    body: str
    score: int
    comments: int
    created_at: int
    source_uri: str


@dataclass(frozen=True)
class TrendSignal:
    source_id: str
    source_uri: str
    theme_hint: str
    velocity: float
    engagement: int
    source_text: None = None
    rights_mode: str = "reference_only"


class RedditSignalExtractor:
    """Converts API metadata into an abstract signal without retaining story text."""

    def extract(self, post: SourcePost, now: int) -> TrendSignal:
        age = max(1, now - post.created_at)
        engagement = max(0, post.score) + max(0, post.comments) * 2
        safe_title = " ".join(post.title.split())[:160]
        return TrendSignal(
            source_id=post.source_id,
            source_uri=post.source_uri,
            theme_hint=safe_title,
            velocity=engagement / age,
            engagement=engagement,
        )

