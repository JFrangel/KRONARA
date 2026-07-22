import subprocess

import pytest

from kronara.render import (
    FfmpegRenderer,
    REEL_9x16,
    MASTER_16x9,
    SubtitleCue,
    build_render_args,
    build_srt,
    cues_from_word_boundaries,
    find_ffmpeg,
)


class _Boundary:
    def __init__(self, word, offset_ms, duration_ms):
        self.word = word
        self.offset_ms = offset_ms
        self.duration_ms = duration_ms


def test_build_srt_formats_timecodes():
    srt = build_srt((SubtitleCue(100, 1600, "Mara escucha"),))
    assert "00:00:00,100 --> 00:00:01,600" in srt
    assert "Mara escucha" in srt


def test_cues_group_words_into_short_lines():
    boundaries = [_Boundary(w, i * 300, 250) for i, w in enumerate("uno dos tres cuatro cinco".split())]
    cues = cues_from_word_boundaries(boundaries, max_chars=12)
    assert len(cues) >= 2
    assert cues[0].start_ms == 0


def test_render_args_have_expected_flags():
    args = build_render_args(
        "ffmpeg", audio_path="a.mp3", output_path="out.mp4", preset=REEL_9x16, subtitle_path="s.srt"
    )
    assert "libx264" in args
    assert "color=c=black:s=1080x1920:r=30" in args
    assert any(a.startswith("subtitles=") for a in args)
    assert "FontSize=10" in next(a for a in args if a.startswith("subtitles="))
    assert args[-1] == "out.mp4"


def test_presets_orientation():
    assert REEL_9x16.height > REEL_9x16.width
    assert MASTER_16x9.width > MASTER_16x9.height


@pytest.mark.skipif(find_ffmpeg("ffmpeg") is None, reason="ffmpeg not installed")
def test_live_render_produces_valid_reel(tmp_path):
    ffmpeg = find_ffmpeg("ffmpeg")
    audio = tmp_path / "tone.mp3"
    # A 2-second tone as a network-free narration stand-in.
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(audio)],
        capture_output=True,
        check=True,
    )
    renderer = FfmpegRenderer()
    result = renderer.render(
        audio_path=str(audio), output_path=str(tmp_path / "reel.mp4"), preset=REEL_9x16
    )
    assert result.qc.passed, result.qc.issues
    assert (result.qc.width, result.qc.height) == (1080, 1920)
    assert result.qc.has_audio is True
    assert 1.5 < result.qc.duration_seconds < 3.0
