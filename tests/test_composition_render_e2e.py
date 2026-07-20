"""V0 milestone: the composition spine proven end-to-end with zero heavyweight
dependencies — Pillow-drawn placeholder shots + ffmpeg `sine=` tones standing
in for narration/music/SFX (the same trick test_render.py already uses).
Produces one real MP4: sequenced animated shots, ducked music, timed SFX,
burned subtitles, passing QC — with no torch, no diffusers, no API keys."""

from __future__ import annotations

import subprocess

import pytest

from kronara.audio_mix import SfxCue, match_sfx_cues
from kronara.composition import (
    VisualAsset,
    build_visual_track_plan,
    plan_shots_for_scene,
    tier_for_scene,
)
from kronara.render import REEL_9x16, FfmpegRenderer, build_srt, cues_from_word_boundaries, find_ffmpeg


class _Boundary:
    def __init__(self, word, offset_ms, duration_ms):
        self.word = word
        self.offset_ms = offset_ms
        self.duration_ms = duration_ms


def _placeholder_png(path, *, width, height, color):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    Image.new("RGB", (width, height), color).save(path)


def _sine_wav(ffmpeg, path, *, frequency, duration_s):
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration_s}", str(path)],
        capture_output=True, check=True,
    )


FFMPEG_MISSING = find_ffmpeg("ffmpeg") is None


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v0_placeholder_pipeline_produces_a_real_composed_reel(tmp_path):
    ffmpeg = find_ffmpeg("ffmpeg")

    # --- fixture data: a 3-scene story with real-shaped per-scene timing ---
    per_scene_ms = (8000, 7000, 6000)  # hook, context, climax-ish close
    total_ms = sum(per_scene_ms)

    # word boundaries across the whole track (global offsets, matching how
    # SceneDurationMeasurer accumulates them across scenes in production)
    word_boundaries = [
        _Boundary("Mara", 200, 300),
        _Boundary("abre", 600, 250),
        _Boundary("la", 900, 100),
        _Boundary("puerta", 1050, 400),
        _Boundary("y", 1500, 100),
        _Boundary("escucha", 1650, 400),
        _Boundary("pasos", 9200, 350),
        _Boundary("en", 9600, 100),
        _Boundary("el", 9700, 100),
        _Boundary("pasillo", 9850, 500),
    ]

    # --- shot plan: one scene gets premium tier (climax), others fast ---
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    palette = [(30, 30, 60), (60, 30, 30), (30, 60, 40), (50, 50, 20)]
    all_shots = []
    for scene_index, duration_ms in enumerate(per_scene_ms):
        tier = tier_for_scene(scene_index, per_scene_ms)
        scene_assets = []
        for i in range(2):
            color = palette[(scene_index * 2 + i) % len(palette)]
            path = assets_dir / f"scn{scene_index}_a{i}.png"
            _placeholder_png(path, width=768, height=1344, color=color)
            scene_assets.append(VisualAsset(f"scn{scene_index}_a{i}", "placeholder", str(path), 768, 1344))
        all_shots.extend(plan_shots_for_scene(f"scn{scene_index}", duration_ms, tier, scene_assets))
    plan = build_visual_track_plan(all_shots, crossfade_ms=400)
    assert plan.total_duration_ms == total_ms
    # the climax scene (index 2, last -> forced premium) should show larger zoom
    climax_shots = [s for s in plan.shots if s.scene_id == "scn2"]
    assert all(s.tier == "premium" for s in climax_shots)

    # --- audio fixtures: narration + music + one sfx clip (real ffmpeg tones) ---
    narration_path = tmp_path / "narration.wav"
    music_path = tmp_path / "music.wav"
    footsteps_path = tmp_path / "footsteps.wav"
    _sine_wav(ffmpeg, narration_path, frequency=220, duration_s=total_ms / 1000)
    _sine_wav(ffmpeg, music_path, frequency=440, duration_s=total_ms / 1000)
    _sine_wav(ffmpeg, footsteps_path, frequency=110, duration_s=0.3)

    sfx_cues = match_sfx_cues(word_boundaries)
    assert any(cue.tag == "door_creak" for cue in sfx_cues)
    assert any(cue.tag == "footsteps" for cue in sfx_cues)
    # Only seed an asset for footsteps -> door_creak cue should be silently
    # dropped by build_mix_filters (missing-asset degrade, not an error).
    sfx_paths = {"footsteps": str(footsteps_path)}

    # --- subtitles from the same word boundaries (already-working v0.6 path) ---
    srt_path = tmp_path / "subs.srt"
    cues = cues_from_word_boundaries(word_boundaries)
    srt_path.write_text(build_srt(cues), encoding="utf-8")

    # --- render the full composition ---
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)
    result = renderer.render_composition(
        visual_plan=plan,
        narration_path=str(narration_path),
        narration_duration_ms=total_ms,
        output_path=str(tmp_path / "episode_v0.mp4"),
        preset=REEL_9x16,
        music_path=str(music_path),
        sfx_cues=sfx_cues,
        sfx_paths=sfx_paths,
        subtitle_path=str(srt_path),
    )

    assert result.qc.passed, result.qc.issues
    assert (result.qc.width, result.qc.height) == (1080, 1920)
    assert result.qc.has_audio is True
    # allow generous slack: xfade/loop timing on placeholder assets, not exact-frame
    assert abs(result.qc.duration_seconds - total_ms / 1000) < 1.0


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v0_composition_without_music_still_renders(tmp_path):
    """No-music path: audio map must be a raw stream selector, not a filter
    label, and the render must still succeed."""
    ffmpeg = find_ffmpeg("ffmpeg")
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    asset_path = assets_dir / "a.png"
    _placeholder_png(asset_path, width=768, height=1344, color=(10, 10, 10))
    asset = VisualAsset("a1", "placeholder", str(asset_path), 768, 1344)
    shots = plan_shots_for_scene("scn0", 4000, "fast", [asset])
    plan = build_visual_track_plan(shots, crossfade_ms=400)

    narration_path = tmp_path / "narration.wav"
    _sine_wav(ffmpeg, narration_path, frequency=220, duration_s=4.0)

    renderer = FfmpegRenderer(ffmpeg=ffmpeg)
    result = renderer.render_composition(
        visual_plan=plan,
        narration_path=str(narration_path),
        narration_duration_ms=4000,
        output_path=str(tmp_path / "episode_no_music.mp4"),
        preset=REEL_9x16,
    )
    assert result.qc.passed, result.qc.issues
    assert result.qc.has_audio is True


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v0_loudness_normalization_two_pass(tmp_path):
    ffmpeg = find_ffmpeg("ffmpeg")
    src = tmp_path / "tone.wav"
    _sine_wav(ffmpeg, src, frequency=1000, duration_s=2.0)
    # wrap the tone in a trivial video so normalize_loudness has a real file
    video_src = tmp_path / "tone.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10:d=2",
         "-i", str(src), "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video_src)],
        capture_output=True, check=True,
    )
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)
    report = renderer.normalize_loudness(str(video_src), str(tmp_path / "normalized.mp4"))
    assert -30.0 < report.integrated_lufs < 0.0


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v4_duck_gain_default_lands_music_18_to_22_lu_below_narration(tmp_path):
    """V4's calibration acceptance criterion, measured for real (not assumed
    from the dB arithmetic alone): narration and music start at comparable
    standalone loudness (the realistic case -- both mastered on their own),
    then DuckingEnvelope's default duck_gain is applied to the music and the
    FLAT ducked region (away from the fade edges) is measured on its own and
    compared against narration's own natural loudness."""
    from kronara.audio_mix import DuckingEnvelope

    ffmpeg = find_ffmpeg("ffmpeg")
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)

    narration_path = tmp_path / "narration.wav"
    music_path = tmp_path / "music.wav"
    _sine_wav(ffmpeg, narration_path, frequency=220, duration_s=10.0)
    _sine_wav(ffmpeg, music_path, frequency=440, duration_s=10.0)  # same default amplitude

    envelope = DuckingEnvelope(narration_start_s=1.0, narration_end_s=9.0, fade_s=0.5)
    ducked_full = tmp_path / "music_ducked_full.wav"
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(music_path),
            "-af", f"volume=eval=frame:volume='{envelope.as_ffmpeg_expression()}'",
            str(ducked_full),
        ],
        capture_output=True, check=True,
    )
    # Trim to well inside the flat-ducked region (envelope is flat 1.5s-8.5s;
    # 2s-8s leaves margin on both sides) so fade ramps don't skew the reading.
    ducked_flat = tmp_path / "music_ducked_flat.wav"
    subprocess.run(
        [ffmpeg, "-y", "-i", str(ducked_full), "-ss", "2", "-to", "8", str(ducked_flat)],
        capture_output=True, check=True,
    )

    narration_report = renderer.measure_loudness(str(narration_path))
    ducked_report = renderer.measure_loudness(str(ducked_flat))
    lu_below_narration = narration_report.integrated_lufs - ducked_report.integrated_lufs

    assert 18.0 <= lu_below_narration <= 22.0, (
        f"narration={narration_report.integrated_lufs} ducked_music={ducked_report.integrated_lufs} "
        f"delta={lu_below_narration} -- expected 18-22 LU"
    )


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v8_qc_black_frame_detection_is_opt_in_and_catches_a_real_black_clip(tmp_path):
    ffmpeg = find_ffmpeg("ffmpeg")
    black_video = tmp_path / "black.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=10:d=2",
         "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", str(black_video)],
        capture_output=True, check=True,
    )
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)

    default_report = renderer.qc(str(black_video), REEL_9x16)
    assert default_report.passed  # opt-in: not requested, not checked
    assert default_report.black_seconds == 0.0

    strict_report = renderer.qc(str(black_video), REEL_9x16, max_black_seconds=0.5)
    assert strict_report.passed is False
    assert "black_frames_detected" in strict_report.issues
    assert strict_report.black_seconds > 1.0


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v8_qc_loudness_range_is_opt_in_and_catches_an_out_of_range_file(tmp_path):
    ffmpeg = find_ffmpeg("ffmpeg")
    src = tmp_path / "quiet_tone.wav"
    video_src = tmp_path / "quiet.mp4"
    # A very quiet tone (low volume factor) lands far outside a -19/-13 LUFS band.
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
         "-af", "volume=0.01", str(src)],
        capture_output=True, check=True,
    )
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=10:d=2",
         "-i", str(src), "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video_src)],
        capture_output=True, check=True,
    )
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)

    default_report = renderer.qc(str(video_src), REEL_9x16)
    assert default_report.passed  # opt-in: not requested, not checked
    assert default_report.integrated_lufs is None

    strict_report = renderer.qc(str(video_src), REEL_9x16, loudness_range_lufs=(-19.0, -13.0))
    assert strict_report.passed is False
    assert "loudness_out_of_range" in strict_report.issues
    assert strict_report.integrated_lufs is not None
    assert strict_report.integrated_lufs < -19.0


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_v8_video_loop_shot_composites_alongside_image_shots(tmp_path):
    """A real moving clip (not a static image) mixed into the same episode
    as ordinary Ken-Burns image shots: proves build_composition_args()
    actually branches on asset.kind (-stream_loop + trim/scale/crop for
    video, -loop 1 + zoompan for images), not just that V6 assigns the
    label. A 1s source clip deliberately shorter than its 4s shot duration
    checks the -stream_loop input keeps it looping to fill the gap."""
    ffmpeg = find_ffmpeg("ffmpeg")
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()

    image_path = assets_dir / "img.png"
    _placeholder_png(image_path, width=768, height=1344, color=(40, 40, 80))
    image_asset = VisualAsset("scn0_a1", "ai_image", str(image_path), 768, 1344)

    clip_path = assets_dir / "clip.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
        capture_output=True, check=True,
    )
    video_asset = VisualAsset("scn1_video", "video_loop", str(clip_path), 640, 360)

    scn0_shots = plan_shots_for_scene("scn0", 4000, "fast", [image_asset])
    scn1_shots = plan_shots_for_scene("scn1", 4000, "fast", [video_asset])
    plan = build_visual_track_plan(scn0_shots + scn1_shots, crossfade_ms=400)
    assert any(shot.asset.kind == "video_loop" for shot in plan.shots)

    narration_path = tmp_path / "narration.wav"
    _sine_wav(ffmpeg, narration_path, frequency=220, duration_s=8.0)

    renderer = FfmpegRenderer(ffmpeg=ffmpeg)
    result = renderer.render_composition(
        visual_plan=plan,
        narration_path=str(narration_path),
        narration_duration_ms=8000,
        output_path=str(tmp_path / "mixed_sources.mp4"),
        preset=REEL_9x16,
    )

    assert result.qc.passed, result.qc.issues
    assert (result.qc.width, result.qc.height) == (1080, 1920)
    assert abs(result.qc.duration_seconds - 8.0) < 1.0
