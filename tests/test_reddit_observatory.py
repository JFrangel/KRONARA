from dataclasses import asdict
import json

from kronara.reddit_observatory import (
    ObservableRedditSignal,
    RedditObservatory,
    RedditSignalFilters,
)


def signal(source_id: str, **overrides) -> ObservableRedditSignal:
    values = {
        "source_id": source_id,
        "source_uri": f"https://reddit.com/r/historias/{source_id}",
        "theme_hint": "conflicto familiar y una decisión moral",
        "score": 120,
        "comments": 45,
        "age_hours": 6.0,
        "language": "es",
        "self_post": True,
        "nsfw": False,
        "author_deleted": False,
        "post_deleted": False,
        "crosspost": False,
        "repost": False,
        "observed_length": 900,
        "velocity": 8.0,
        "acceleration": 1.5,
        "saturation": 0.2,
        "lifetime_hours": 18.0,
    }
    values.update(overrides)
    return ObservableRedditSignal(**values)


def filters(**overrides) -> RedditSignalFilters:
    values = {
        "min_score": 50,
        "max_score": 5000,
        "min_comments": 20,
        "max_comments": 2000,
        "min_age_hours": 0.0,
        "max_age_hours": 24.0,
        "language": "es",
        "self_posts_only": True,
        "include_nsfw": False,
        "include_keywords": ("decisión",),
        "exclude_keywords": ("política",),
        "min_length": 100,
        "max_length": 5000,
        "allow_deleted": False,
        "allow_crossposts": False,
        "allow_reposts": False,
        "min_velocity": 4.0,
        "min_acceleration": 0.0,
        "max_saturation": 0.8,
        "min_lifetime_hours": 6.0,
        "semantic_dedup_threshold": 0.9,
    }
    values.update(overrides)
    return RedditSignalFilters(**values)


def test_filters_score_comments_age_language_safety_and_velocity():
    result = RedditObservatory().filter(
        (
            signal("accepted"),
            signal("low_score", score=1),
            signal("wrong_language", language="en"),
            signal("unsafe", nsfw=True),
            signal("slow", velocity=0.1),
        ),
        filters(),
    )

    assert [item.source_id for item in result.signals] == ["accepted"]
    assert result.rejected_by_reason == {
        "score": 1,
        "language": 1,
        "nsfw": 1,
        "velocity": 1,
    }


def test_external_body_is_absent_and_duplicate_signals_collapse():
    result = RedditObservatory().filter(
        (
            signal("first"),
            signal(
                "duplicate",
                source_uri="https://reddit.com/r/historias/first",
                score=100,
            ),
        ),
        filters(),
    )
    encoded = json.dumps(asdict(result), ensure_ascii=False)

    assert [item.source_id for item in result.signals] == ["first"]
    assert "body" not in encoded
    assert "selftext" not in encoded
    assert result.rejected_by_reason == {"duplicate": 1}


def test_keyword_crosspost_deleted_saturation_and_lifetime_filters_are_visible():
    result = RedditObservatory().filter(
        (
            signal("excluded_word", theme_hint="política local y una decisión"),
            signal("crosspost", crosspost=True),
            signal("deleted", post_deleted=True),
            signal("saturated", saturation=0.95),
            signal("short_lived", lifetime_hours=2.0),
        ),
        filters(),
    )

    assert result.signals == ()
    assert result.rejected_by_reason == {
        "excluded_keyword": 1,
        "crosspost": 1,
        "deleted": 1,
        "saturation": 1,
        "lifetime": 1,
    }

