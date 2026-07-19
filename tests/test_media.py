import pytest

from kronara.media import MediaTimeline, TimelineValidator, Track


def test_reel_timeline_requires_vertical_canvas_and_voice():
    timeline = MediaTimeline(width=1920, height=1080, duration_ms=30_000, tracks=())

    with pytest.raises(ValueError, match="vertical canvas"):
        TimelineValidator().validate_reel(timeline)


def test_valid_reel_timeline_has_voice_inside_duration():
    timeline = MediaTimeline(
        width=1080,
        height=1920,
        duration_ms=30_000,
        tracks=(Track("voice", 0, 30_000), Track("subtitles", 0, 30_000)),
    )

    assert TimelineValidator().validate_reel(timeline) is True

