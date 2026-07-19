from datetime import UTC, datetime, timedelta

import pytest

from kronara.performance import MetricSnapshot, PerformanceScientist


PUBLISHED = datetime(2026, 7, 19, 12, tzinfo=UTC)


def test_metric_snapshot_rejects_invalid_funnel_denominators():
    with pytest.raises(ValueError, match="completions"):
        _snapshot("bad", voice="voice-a", starts=10, completions=11)


def test_performance_scientist_abstains_when_sample_is_insufficient():
    diagnosis = PerformanceScientist(minimum_total_starts=200).diagnose(
        (_snapshot("small", voice="voice-a", starts=20, completions=15),)
    )

    assert diagnosis.status == "insufficient_data"
    assert diagnosis.hypotheses == ()
    assert "insufficient_total_sample" in diagnosis.warnings
    assert "observational_not_causal" in diagnosis.warnings


def test_voice_finding_uses_intervals_and_proposes_non_causal_hypothesis():
    snapshots = tuple(
        _snapshot(f"a-{index}", voice="voice-a", starts=100, completions=60)
        for index in range(3)
    ) + tuple(
        _snapshot(f"b-{index}", voice="voice-b", starts=100, completions=40)
        for index in range(3)
    )

    diagnosis = PerformanceScientist(
        minimum_total_starts=200,
        minimum_segment_starts=200,
        minimum_segment_pieces=2,
        minimum_lift=0.05,
    ).diagnose(snapshots)

    voice_findings = [item for item in diagnosis.segments if item.dimension == "voice"]
    best = next(item for item in voice_findings if item.value == "voice-a")
    hypothesis = next(item for item in diagnosis.hypotheses if item.dimension == "voice")
    assert diagnosis.status == "ready_for_experiment"
    assert best.completion_rate == 0.6
    assert best.interval[0] < best.completion_rate < best.interval[1]
    assert hypothesis.candidate_value == "voice-a"
    assert hypothesis.minimum_sample_per_variant > 0
    assert "asociada" in hypothesis.statement
    assert "causa" not in hypothesis.statement
    assert hypothesis.causal_claim is False


def test_diagnosis_segments_every_editorial_dimension_without_pooling_platforms():
    snapshots = (
        _snapshot("one", voice="voice-a", starts=150, completions=75),
        _snapshot(
            "two",
            voice="voice-b",
            starts=150,
            completions=60,
            topic="misterio",
            hook="pregunta",
            duration_seconds=75,
            publication_hour=21,
            audience="returning",
        ),
    )
    diagnosis = PerformanceScientist(
        minimum_total_starts=100,
        minimum_segment_starts=50,
        minimum_segment_pieces=1,
    ).diagnose(snapshots)

    assert {item.dimension for item in diagnosis.segments} == {
        "voice",
        "topic",
        "hook",
        "duration",
        "publication_time",
        "audience",
    }
    assert diagnosis.platform == "facebook_reels"

    with pytest.raises(ValueError, match="one platform"):
        PerformanceScientist().diagnose(
            snapshots
            + (
                _snapshot(
                    "youtube",
                    voice="voice-a",
                    starts=100,
                    completions=50,
                    platform="youtube_shorts",
                ),
            )
        )


def test_diagnosis_trace_is_reproducible_for_the_same_snapshots():
    snapshots = (
        _snapshot("one", voice="voice-a", starts=150, completions=75),
        _snapshot("two", voice="voice-b", starts=150, completions=60),
    )
    scientist = PerformanceScientist(minimum_total_starts=100)

    first = scientist.diagnose(snapshots)
    second = scientist.diagnose(tuple(reversed(snapshots)))

    assert first.input_hash == second.input_hash
    assert len(first.input_hash) == 64


def _snapshot(
    snapshot_id: str,
    *,
    voice: str,
    starts: int,
    completions: int,
    platform: str = "facebook_reels",
    topic: str = "suspenso",
    hook: str = "confesion",
    duration_seconds: float = 45,
    publication_hour: int = 12,
    audience: str = "broad",
) -> MetricSnapshot:
    return MetricSnapshot(
        schema_version=1,
        snapshot_id=snapshot_id,
        content_id=f"content-{snapshot_id}",
        platform=platform,
        published_at=PUBLISHED + timedelta(minutes=len(snapshot_id)),
        observed_at=PUBLISHED + timedelta(hours=48),
        metric_window_hours=48,
        impressions=max(starts, 1) * 2,
        starts=starts,
        completions=completions,
        replays=max(0, completions // 5),
        shares=max(0, completions // 10),
        watch_time_seconds=float(starts * duration_seconds * 0.55),
        duration_seconds=duration_seconds,
        voice_id=voice,
        topic=topic,
        hook_id=hook,
        publication_hour=publication_hour,
        audience_segment=audience,
    )
