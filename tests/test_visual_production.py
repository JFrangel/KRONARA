"""The V8 capstone: the full V0-V6 chain (shot planning, image generation,
hybrid source assignment, composition, mix, loudnorm, extended QC) driven
by one produce_episode_video() call, end to end with real ffmpeg. Images use
PlaceholderImageProvider (no GPU needed, same precedent as V0); narration
audio is real ffmpeg tones standing in for edge-tts output, matching how
test_composition_render_e2e.py already proves the render layer."""

from __future__ import annotations

import subprocess

import pytest
from pathlib import Path

from kronara.asset_library import AssetLibraryStore, LibraryAsset
from kronara.image_gen import ImageGenerationResult, PlaceholderImageProvider
from kronara.render import FfmpegRenderer, find_ffmpeg
from kronara.story_engine import StoryScene
from kronara.visual_production import build_shot_prompt
from kronara.visual_production import _resolve_scene_asset
from kronara.visual_production import produce_episode_video
from kronara.visual_production import render_graphic_overlay_card
from kronara.visual_director import ShotAssignment
from kronara.visual_style import VisualStyleDescriptor
from kronara.voice import MeasuredDuration, WordBoundary

FFMPEG_MISSING = find_ffmpeg("ffmpeg") is None


def test_visual_prompt_adds_literal_anchors_and_contradiction_negatives_for_water_scene():
    prompt, negative = build_shot_prompt(
        "La marea baja deja al descubierto el muelle y las redes mojadas.",
        "",
        None,
    )

    assert "wet wooden dock" in prompt
    assert "low tide" in prompt
    assert "desert" in negative
    assert "car" in negative


def test_visual_prompt_keeps_episode_context_for_short_later_scene():
    prompt, negative = build_shot_prompt(
        "La sombra aparece junto al sofa.",
        "",
        None,
        episode_context="old haunted house interior, bedroom corner, closet door, shadow figure",
        scene_position="scene 4/6",
    )

    assert "scene 4/6" in prompt
    assert "old haunted house interior" in prompt
    assert "shadow figure" in prompt
    assert "current scene: La sombra aparece" in prompt
    assert "unrelated desert" in negative
    assert "random vehicle" in negative


def test_scene_ai_image_uses_cover_as_visual_reference(tmp_path):
    class RecordingProvider:
        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
            path = tmp_path / "scene.png"
            path.write_bytes(b"png")
            return ImageGenerationResult(str(path), request.seed, request.width, request.height, request.quality_tier, 1)

    cover = tmp_path / "cover.png"
    cover.write_bytes(b"png")
    provider = RecordingProvider()

    _resolve_scene_asset(
        scene=StoryScene("scn1", "reveal", "La figura espera junto al armario.", 10, (), (), ()),
        assignment=ShotAssignment("scn1", "ai_image"),
        tier="fast",
        output_dir=str(tmp_path),
        image_provider=provider,
        visual_style=None,
        negative_prompt="",
        episode_context="old haunted house interior, shadow figure",
        scene_index=1,
        total_scenes=3,
        reference_image_path=str(cover),
    )

    assert provider.requests[0].reference_image_path == str(cover)
    assert provider.requests[0].reference_strength == 0.45


def test_graphic_overlay_card_matches_dark_visual_language(tmp_path):
    from PIL import Image

    path = tmp_path / "overlay.png"
    render_graphic_overlay_card(
        "Mara escucha una llamada desde un teléfono desconectado",
        str(path),
        width=1080,
        height=1920,
    )
    image = Image.open(path).convert("RGB")
    assert image.size == (1080, 1920)
    assert image.getpixel((0, 0)) != (245, 244, 240)
    assert image.getpixel((0, 0)) != image.getpixel((540, 960))


def _sine(ffmpeg, path, *, frequency, duration_s):
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration_s}", str(path)],
        capture_output=True, check=True,
    )


def _clip(ffmpeg, path, *, duration_s=1):
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=24:duration={duration_s}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=True,
    )


def _style(tmp_path) -> VisualStyleDescriptor:
    return VisualStyleDescriptor(
        program_id="viernes-paranormal", display_name="Viernes Paranormal", weekday="viernes",
        style_prompt="dark blue and sickly green palette, fog", negative_prompt="bright colors",
        motion_bias="subtle", music_moods=("paranormal-tension",), asset_tags=("fog",),
    )


def _library(tmp_path, ffmpeg) -> AssetLibraryStore:
    lib = AssetLibraryStore(tmp_path / "lib.db").initialize()
    music_path = tmp_path / "music.wav"
    _sine(ffmpeg, music_path, frequency=440, duration_s=15.0)
    lib.seed(LibraryAsset(
        asset_type="music", tags=("paranormal-tension",), file_path=str(music_path),
        duration_ms=15000, rights_mode="cc0", source_url="https://freesound.org/", added_at=100,
    ))
    clip_path = tmp_path / "fog_clip.mp4"
    _clip(ffmpeg, clip_path, duration_s=1)
    lib.seed(LibraryAsset(
        asset_type="video_loop", tags=("fog",), file_path=str(clip_path),
        duration_ms=1000, rights_mode="pexels_license", source_url="https://pexels.com/video/1",
        added_at=100,
    ))
    footsteps_path = tmp_path / "footsteps.wav"
    _sine(ffmpeg, footsteps_path, frequency=110, duration_s=0.3)
    lib.seed(LibraryAsset(
        asset_type="sfx", tags=("footsteps",), file_path=str(footsteps_path),
        duration_ms=300, rights_mode="cc0", source_url="https://freesound.org/", added_at=100,
    ))
    return lib


def _scenes():
    return (
        StoryScene("scn0", "hook", "Mara escucha pasos en el pasillo oscuro", 5, (), (), ()),
        StoryScene("scn1", "context", "Revisa el documento que encontró bajo la puerta", 5, (), (), ()),
        StoryScene("scn2", "climax", "El silencio se vuelve insoportable", 5, (), (), ()),
    )


def _voice_duration(tmp_path, ffmpeg) -> MeasuredDuration:
    per_scene_ms = (5000, 5000, 5000)
    audio_refs = []
    for index, freq in enumerate((220, 260, 300)):
        path = tmp_path / f"scene{index}.wav"
        _sine(ffmpeg, path, frequency=freq, duration_s=5.0)
        audio_refs.append(str(path))
    word_boundaries = (
        WordBoundary("pasos", 500, 300),
        WordBoundary("puerta", 5200, 400),
        WordBoundary("silencio", 11000, 500),
    )
    return MeasuredDuration(
        total_seconds=15.0, per_scene_ms=per_scene_ms, word_boundaries=word_boundaries,
        degraded=False, audio_refs=tuple(audio_refs),
    )


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_produce_episode_video_full_chain(tmp_path):
    ffmpeg = find_ffmpeg("ffmpeg")
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)
    library = _library(tmp_path, ffmpeg)
    image_provider = PlaceholderImageProvider(output_dir=str(tmp_path / "images"))

    result = produce_episode_video(
        scenes=_scenes(),
        voice_duration=_voice_duration(tmp_path, ffmpeg),
        output_dir=str(tmp_path / "episode"),
        episode_id="ep1",
        renderer=renderer,
        image_provider=image_provider,
        visual_style=_style(tmp_path),
        library=library,
    )

    assert result.qc.passed, result.qc.issues
    assert (result.qc.width, result.qc.height) == (1080, 1920)
    assert abs(result.qc.duration_seconds - 15.0) < 1.5
    assert result.scene_count == 3
    assert sum(result.source_kind_counts.values()) == 3
    assert -19.0 <= result.loudness.integrated_lufs <= -13.0
    assert result.cover_image_path
    assert Path(result.cover_image_path).exists()
    assert result.music_path
    assert "footsteps" in result.sfx_cue_tags
    assert result.sfx_resolved_paths["footsteps"] == str(tmp_path / "footsteps.wav")
    library.close()


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_produce_episode_video_without_library_still_renders(tmp_path):
    """No library at all: video_loop can never fire (nothing to match
    against) and must always degrade to ai_image ('ninguna toma queda sin
    recurso') -- graphic_overlay is unaffected since it's driven by
    narration text alone, not the library, and scn1's narration ("...el
    documento...") is expected to still trigger it."""
    ffmpeg = find_ffmpeg("ffmpeg")
    renderer = FfmpegRenderer(ffmpeg=ffmpeg)
    image_provider = PlaceholderImageProvider(output_dir=str(tmp_path / "images"))

    result = produce_episode_video(
        scenes=_scenes(),
        voice_duration=_voice_duration(tmp_path, ffmpeg),
        output_dir=str(tmp_path / "episode2"),
        episode_id="ep2",
        renderer=renderer,
        image_provider=image_provider,
    )

    assert result.qc.passed, result.qc.issues
    assert result.source_kind_counts["video_loop"] == 0
    assert sum(result.source_kind_counts.values()) == 3
    assert result.cover_image_path
    assert Path(result.cover_image_path).exists()


def test_missing_audio_ref_raises_a_clear_error(tmp_path):
    from kronara.render import FfmpegRenderer
    from kronara.image_gen import PlaceholderImageProvider as _Placeholder

    voice_duration = MeasuredDuration(
        total_seconds=5.0, per_scene_ms=(5000,), word_boundaries=(), degraded=False,
        audio_refs=("",),  # provider never wrote a file (e.g. EstimatingVoiceProvider)
    )
    with pytest.raises(ValueError, match="real per-scene narration audio"):
        produce_episode_video(
            scenes=(StoryScene("scn0", "hook", "texto", 5, (), (), ()),),
            voice_duration=voice_duration,
            output_dir=str(tmp_path / "episode3"),
            episode_id="ep3",
            renderer=FfmpegRenderer(ffmpeg="ffmpeg"),
            image_provider=_Placeholder(output_dir=str(tmp_path)),
        )


def test_scene_count_mismatch_raises_a_clear_error(tmp_path):
    from kronara.render import FfmpegRenderer
    from kronara.image_gen import PlaceholderImageProvider as _Placeholder

    voice_duration = MeasuredDuration(
        total_seconds=5.0, per_scene_ms=(5000,), word_boundaries=(), degraded=False,
        audio_refs=("/some/path.mp3",),
    )
    with pytest.raises(ValueError, match="one entry per scene"):
        produce_episode_video(
            scenes=(
                StoryScene("scn0", "hook", "texto", 5, (), (), ()),
                StoryScene("scn1", "close", "texto2", 5, (), (), ()),
            ),
            voice_duration=voice_duration,
            output_dir=str(tmp_path / "episode4"),
            episode_id="ep4",
            renderer=FfmpegRenderer(ffmpeg="ffmpeg"),
            image_provider=_Placeholder(output_dir=str(tmp_path)),
        )
