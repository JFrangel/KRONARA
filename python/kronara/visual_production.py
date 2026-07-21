"""Wires the visual pipeline (V0-V6) into one call: approved story scenes +
measured narration -> shot plan -> image generation (program-styled) ->
hybrid source assignment -> composition -> mix -> loudnorm -> extended QC.
This is what V8 adds between "script approved" and "final MP4" in
content_pipeline.py.

Source-kind assignment (V6) runs once PER SCENE, not per eventual 3-7s
sub-shot: a scene's sub-shots all share one visual treatment, matching how a
single narrative beat is normally shot in practice, and bounding image-
generation cost to one real image per scene (Ken Burns motion still varies
sub-shot to sub-shot on that one image via plan_shots_for_scene's per-index
pan/zoom rotation).

Character-visual consistency (V2) is deliberately NOT wired here yet: it
needs a text appearance description per character, which today only exists
for series stories tracked via SeriesCanonBuilder, not standalone ones. This
module generates images straight from scene narration text; layering V2 in
for the series case is a follow-up, not a blocker for a real end-to-end MP4.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from kronara.asset_library import AssetLibraryStore, LibraryAsset, sfx_paths_from_library
from kronara.audio_mix import DEFAULT_KEYWORD_SFX, match_sfx_cues
from kronara.composition import (
    DEFAULT_CROSSFADE_MS,
    Shot,
    VisualAsset,
    build_visual_track_plan,
    plan_shots_for_scene,
    tier_for_scene,
)
from kronara.image_gen import SDXL_BUCKET_9x16, ImageGenerationRequest
from kronara.render import REEL_9x16, FfmpegRenderer, LoudnessReport, QCReport, RenderPreset, build_srt, cues_from_word_boundaries
from kronara.visual_director import assign_visual_sources
from kronara.visual_style import VisualStyleDescriptor, apply_style
from kronara.voice import MeasuredDuration

# Sentinel used only to give assign_visual_sources a (shot_id, scene_id)
# identity per scene; its duration/tier/asset fields are never read for a
# real render since every scene's actual shots are re-planned afterward.
_SENTINEL_ASSET = VisualAsset("sentinel", "placeholder", "", 1, 1)


@dataclass(frozen=True)
class VisualProductionResult:
    output_path: str
    qc: QCReport
    loudness: LoudnessReport
    scene_count: int
    shot_count: int
    source_kind_counts: dict
    cover_image_path: str = ""


def concatenate_audio(ffmpeg: str, paths: Sequence[str], output_path: str, *, timeout: int = 300) -> None:
    """Join per-scene audio files in order via ffmpeg's concat demuxer.
    Re-encodes (``-c:a libmp3lame``) rather than stream-copying: production
    audio_refs are real same-format mp3s from EdgeTtsVoiceProvider, where a
    stream copy would work, but re-encoding costs nothing noticeable on a
    few scenes of narration and stays correct regardless of what format a
    future voice provider happens to write."""
    if not paths:
        raise ValueError("at least one audio path is required")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    list_path = f"{output_path}.concat.txt"
    with open(list_path, "w", encoding="utf-8") as handle:
        for path in paths:
            escaped = str(Path(path).resolve()).replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    try:
        completed = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c:a", "libmp3lame", output_path],
            capture_output=True, text=True, timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"narration concat failed: {completed.stderr[-500:]}")
    finally:
        os.remove(list_path)


def build_shot_prompt(
    narration: str, negative_prompt: str, style: VisualStyleDescriptor | None
) -> tuple[str, str]:
    base = " ".join(narration.split())  # collapse whitespace; CLIP truncates long prompts itself
    base_prompt = f"cinematic photograph, vertical composition, {base}" if base else "cinematic photograph"
    return apply_style(base_prompt, negative_prompt, style)


def render_graphic_overlay_card(text: str, output_path: str, *, width: int, height: int) -> None:
    """A recreated document/message card -- Pillow-drawn, not SD-generated
    (SDXL is not reliable for coherent text/UI, per V6's design)."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), (245, 244, 240))
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.1)
    draw.rectangle(
        [margin // 2, margin, width - margin // 2, height - margin], outline=(60, 60, 60), width=3
    )
    wrapped = _wrap_text(" ".join(text.split()), max_chars=28)
    line_height = 44
    start_y = height // 2 - (len(wrapped) * line_height) // 2
    for index, line in enumerate(wrapped[:14]):
        draw.text((margin, start_y + index * line_height), line, fill=(30, 30, 30))
    os.makedirs(Path(output_path).parent, exist_ok=True)
    image.save(output_path)


def _wrap_text(text: str, *, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > max_chars and current:
            lines.append(" ".join(current))
            current, length = [], 0
        current.append(word)
        length += len(word) + 1
    if current:
        lines.append(" ".join(current))
    return lines


def select_music_track(library: AssetLibraryStore, moods: Sequence[str]) -> LibraryAsset | None:
    for mood in moods:
        candidates = library.by_tag("music", mood, limit=1)
        if candidates:
            library.mark_used(candidates[0].asset_id)
            return candidates[0]
    return None


def _seed_for_shot(scene_id: str) -> int:
    import hashlib

    return int(hashlib.sha256(scene_id.encode("utf-8")).hexdigest()[:8], 16)


def _resolve_scene_asset(
    *,
    scene,
    assignment,
    tier: str,
    output_dir: str,
    image_provider,
    visual_style: VisualStyleDescriptor | None,
    negative_prompt: str,
) -> VisualAsset:
    if assignment.source_kind == "video_loop" and assignment.video_loop_asset is not None:
        video = assignment.video_loop_asset
        width, height = SDXL_BUCKET_9x16
        return VisualAsset(f"{scene.scene_id}_video", "video_loop", video.file_path, width, height)
    if assignment.source_kind == "graphic_overlay":
        width, height = SDXL_BUCKET_9x16
        path = os.path.join(output_dir, f"{scene.scene_id}_overlay.png")
        render_graphic_overlay_card(scene.narration, path, width=width, height=height)
        return VisualAsset(f"{scene.scene_id}_overlay", "graphic_overlay", path, width, height)
    prompt, negative = build_shot_prompt(scene.narration, negative_prompt, visual_style)
    request = ImageGenerationRequest(
        prompt=prompt, negative_prompt=negative, seed=_seed_for_shot(scene.scene_id),
        quality_tier=tier,
    )
    result = image_provider.generate(request)
    return VisualAsset(f"{scene.scene_id}_ai", "ai_image", result.image_path, result.width, result.height)


def generate_cover_image(
    *,
    cover_text: str,
    output_dir: str,
    episode_id: str,
    image_provider,
    visual_style: VisualStyleDescriptor | None = None,
    negative_prompt: str = "",
) -> str:
    """One dedicated poster-style image per episode, always premium tier and
    always a real AI image (never a video-loop frame or a text-card graphic)
    regardless of how the per-scene V6 source assignment turns out -- a
    thumbnail needs to look like a poster, not whatever scene 1 happened to
    be assigned. Built from the story's hook/logline, not scene 1's
    narration, so it reads as a single striking image rather than "the first
    beat of the story." Reuses the same style/prompt pipeline (build_shot_
    prompt + apply_style) so it stays visually consistent with the episode's
    own scenes and the program's visual identity."""
    prompt, negative = build_shot_prompt(cover_text, negative_prompt, visual_style)
    request = ImageGenerationRequest(
        prompt=prompt, negative_prompt=negative,
        seed=_seed_for_shot(f"{episode_id}_cover"), quality_tier="premium",
    )
    result = image_provider.generate(request)
    return result.image_path


def produce_episode_video(
    *,
    scenes: Sequence,
    voice_duration: MeasuredDuration,
    output_dir: str,
    episode_id: str,
    renderer: FfmpegRenderer,
    image_provider,
    preset: RenderPreset = REEL_9x16,
    visual_style: VisualStyleDescriptor | None = None,
    library: AssetLibraryStore | None = None,
    negative_prompt: str = "",
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
    cover_text: str = "",
) -> VisualProductionResult:
    if len(voice_duration.per_scene_ms) != len(scenes):
        raise ValueError("voice_duration must have exactly one entry per scene")
    if any(not ref for ref in voice_duration.audio_refs):
        raise ValueError(
            "real per-scene narration audio is required to produce video "
            "(use a voice provider that writes audio_dir, e.g. EdgeTtsVoiceProvider)"
        )

    os.makedirs(output_dir, exist_ok=True)
    cover_image_path = ""
    if cover_text.strip():
        try:
            cover_image_path = generate_cover_image(
                cover_text=cover_text, output_dir=output_dir, episode_id=episode_id,
                image_provider=image_provider, visual_style=visual_style,
                negative_prompt=negative_prompt,
            )
        except Exception:
            # A missing/broken cover is never worth failing the whole
            # episode over -- the scenes' own images still carry the video.
            cover_image_path = ""
    narration_path = os.path.join(output_dir, f"{episode_id}_narration.mp3")
    concatenate_audio(renderer.ffmpeg, voice_duration.audio_refs, narration_path)
    total_duration_ms = sum(voice_duration.per_scene_ms)

    scene_texts = {scene.scene_id: scene.narration for scene in scenes}
    scene_placeholder_shots = tuple(
        Shot(scene.scene_id, scene.scene_id, _SENTINEL_ASSET, 1000, "fast", 1.0, 1.1, "center_in")
        for scene in scenes
    )
    asset_tags = visual_style.asset_tags if visual_style else ()
    assignments = {
        item.shot_id: item
        for item in assign_visual_sources(
            scene_placeholder_shots, scene_texts, library=library, asset_tags=asset_tags
        )
    }

    all_shots: list[Shot] = []
    source_counts = {"ai_image": 0, "video_loop": 0, "graphic_overlay": 0}
    motion_bias = visual_style.motion_bias if visual_style else "standard"
    for index, scene in enumerate(scenes):
        tier = tier_for_scene(index, voice_duration.per_scene_ms)
        assignment = assignments[scene.scene_id]
        source_counts[assignment.source_kind] += 1
        asset = _resolve_scene_asset(
            scene=scene, assignment=assignment, tier=tier, output_dir=output_dir,
            image_provider=image_provider, visual_style=visual_style,
            negative_prompt=negative_prompt,
        )
        all_shots.extend(
            plan_shots_for_scene(
                scene.scene_id, voice_duration.per_scene_ms[index], tier, [asset],
                motion_bias=motion_bias,
            )
        )

    plan = build_visual_track_plan(all_shots, crossfade_ms=crossfade_ms)

    srt_path = os.path.join(output_dir, f"{episode_id}.srt")
    cues = cues_from_word_boundaries(voice_duration.word_boundaries)
    Path(srt_path).write_text(build_srt(cues), encoding="utf-8")

    sfx_cues = match_sfx_cues(voice_duration.word_boundaries, keyword_map=DEFAULT_KEYWORD_SFX)
    sfx_paths = (
        sfx_paths_from_library(library, {cue.tag for cue in sfx_cues}) if library is not None else {}
    )

    music_path = None
    if library is not None and visual_style is not None and visual_style.music_moods:
        music_asset = select_music_track(library, visual_style.music_moods)
        music_path = music_asset.file_path if music_asset else None

    raw_output_path = os.path.join(output_dir, f"{episode_id}_raw.mp4")
    renderer.render_composition(
        visual_plan=plan,
        narration_path=narration_path,
        narration_duration_ms=total_duration_ms,
        output_path=raw_output_path,
        preset=preset,
        music_path=music_path,
        sfx_cues=sfx_cues,
        sfx_paths=sfx_paths,
        subtitle_path=srt_path,
    )

    output_path = os.path.join(output_dir, f"{episode_id}.mp4")
    loudness = renderer.normalize_loudness(raw_output_path, output_path)
    qc = renderer.qc(output_path, preset, max_black_seconds=0.5, loudness_range_lufs=(-19.0, -13.0))

    return VisualProductionResult(
        output_path=output_path,
        qc=qc,
        loudness=loudness,
        scene_count=len(scenes),
        shot_count=len(plan.shots),
        source_kind_counts=source_counts,
        cover_image_path=cover_image_path,
    )
