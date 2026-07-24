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
from typing import Callable, Sequence

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
from kronara.image_gen import FAST_STEPS, PREMIUM_STEPS
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
    music_path: str = ""
    sfx_cue_tags: tuple[str, ...] = ()
    sfx_resolved_paths: dict[str, str] | None = None
    sfx_missing_tags: tuple[str, ...] = ()


def concatenate_audio(ffmpeg: str, paths: Sequence[str], output_path: str, *, timeout: int = 300) -> None:
    """Join per-scene audio files in order via ffmpeg's concat demuxer.
    Re-encodes (``-c:a libmp3lame``) rather than stream-copying: production
    audio_refs come from VoiceBoxVoiceProvider (wav), and re-encoding to a
    single mp3 track costs nothing noticeable on a few scenes of narration and
    stays correct regardless of what format a voice provider happens to write."""
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
    narration: str,
    negative_prompt: str,
    style: VisualStyleDescriptor | None,
    *,
    episode_context: str = "",
    scene_position: str = "",
) -> tuple[str, str]:
    base = " ".join(narration.split())  # collapse whitespace; CLIP truncates long prompts itself
    context = " ".join(episode_context.split())
    anchors, contradictions = _visual_anchors_for(f"{context} {base}")
    visual_text = " ".join(base.split()[:70])
    # A named master style (anime, watercolor, pixel art...) already fixes its
    # own medium in style_prompt; forcing "cinematic photograph" on top would
    # fight it, so only the legacy additive styles get the photographic default.
    master_style = getattr(style, "is_master_style", False)
    parts = [
        *([] if master_style else ["cinematic photograph"]),
        "vertical composition",
        "scene-matched literal visual",
        "consistent episode setting and recurring characters",
    ]
    if scene_position:
        parts.append(scene_position)
    if context:
        parts.append(f"episode visual context: {context}")
    if visual_text:
        parts.append(f"current scene: {visual_text}")
    if anchors:
        parts.append(anchors)
    base_prompt = ", ".join(parts)
    combined_negative = _join_prompt_parts(
        negative_prompt,
        contradictions,
        "unrelated desert, unrelated car, unrelated highway, random vehicle, random landscape, mismatched location, inconsistent setting",
    )
    return apply_style(base_prompt, combined_negative, style)


def _join_prompt_parts(*values: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in str(value or "").split(","):
            clean = part.strip()
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                parts.append(clean)
    return ", ".join(parts)


def _visual_anchors_for(text: str) -> tuple[str, str]:
    low = text.casefold()
    anchors: list[str] = []
    negatives: list[str] = []
    if any(term in low for term in ("marea", "agua", "muelle", "mar", "redes", "ostiones")):
        anchors.append("wet wooden dock, low tide, ocean water, fishing nets, damp night air")
        negatives.append("desert, dry road, car, highway, sand dunes")
    if any(term in low for term in ("figura", "sombra", "entidad", "fantasma", "aparicion", "aparición")):
        anchors.append("dark humanlike silhouette, shadow figure, supernatural presence, deep corner darkness")
        negatives.append("ordinary person posing, smiling face, clean studio portrait")
    if any(term in low for term in ("habitacion", "habitación", "armario", "pasillo", "sofa", "sofá", "puerta", "esquina")):
        anchors.append("old haunted house interior, bedroom corner, closet door, narrow hallway, practical lamp")
        negatives.append("open desert landscape, city street, car interior")
    return ", ".join(dict.fromkeys(anchors)), ", ".join(dict.fromkeys(negatives))


def _episode_visual_context(
    scenes: Sequence,
    visual_style: VisualStyleDescriptor | None,
    *,
    max_words: int = 44,
    character_descriptions: "dict[str, str] | None" = None,
) -> str:
    narrations = " ".join(
        " ".join(str(getattr(scene, "narration", "")).split())
        for scene in scenes
    )
    anchors, _ = _visual_anchors_for(narrations)
    story_world = " ".join(narrations.split()[:max_words])
    master_style = getattr(visual_style, "is_master_style", False)
    parts: list[str] = []
    if visual_style is not None:
        # Legacy descriptors expose display_name; named styles expose name.
        label = getattr(visual_style, "display_name", None) or getattr(visual_style, "name", "")
        if label:
            parts.append(f"{label} visual identity")
        # program_id only exists on legacy per-program descriptors; named
        # horror styles (analog-horror-vhs) already encode the threat/silhouette
        # in their own style_prompt, so this special-case is legacy-only.
        if getattr(visual_style, "program_id", None) == "viernes-paranormal":
            parts.append("supernatural horror with a visible ghost, entity or shadow presence")
    # Consistency anchors: every scene share these so hosted providers
    # (Pollinations/Cloudflare Flux) that don't take a reference image
    # still land close enough visually across shots that the episode
    # reads as one story instead of a slideshow of disconnected photos.
    # See docs/BUGS_CONOCIDOS.md consistency finding.
    descriptions = character_descriptions or {}
    dominant = _dominant_character_names(scenes)
    if dominant:
        parts.append(f"recurring characters throughout the episode: {', '.join(dominant)}")
        # Canonical per-character appearance (the character bible) pins the SAME
        # face/wardrobe/age in every shot -- the load-bearing lever on hosted
        # Flux providers, which ignore reference images. Falls back to the
        # generic "same faces" anchor when no bible was generated.
        canon = [
            f"{name}: {descriptions[name.casefold()]}"
            for name in dominant
            if name.casefold() in descriptions
        ]
        if canon:
            parts.append("consistent character design -- " + "; ".join(canon))
        else:
            parts.append("same faces, same wardrobe, same age and features across every shot")
    parts.append("consistent color palette, consistent lighting mood, consistent location")
    # Film-stock/grain wording is a photographic-realism default: keep it for
    # legacy styles but drop it for named master styles so pixel-art, watercolor
    # or paper-cutout episodes aren't pushed back toward looking like film.
    if not master_style:
        parts.append("shot on 35mm film stock, warm shadows, filmic grain, cinematic depth")
    if anchors:
        parts.append(anchors)
    if story_world:
        parts.append(f"story world: {story_world}")
    return ". ".join(dict.fromkeys(parts))


def _dominant_character_names(scenes: Sequence, limit: int = 3) -> list[str]:
    """Top-N recurring character names across every scene, most frequent first."""
    from collections import Counter

    tally: Counter[str] = Counter()
    for scene in scenes:
        for name in getattr(scene, "characters", ()) or ():
            clean = str(name).strip()
            if clean:
                tally[clean] += 1
    return [name for name, _ in tally.most_common(limit)]


def _dominant_characters(scenes: Sequence, limit: int = 3) -> str:
    """Extract the top-N recurring character names across every scene so
    every shot prompt carries the same protagonist(s). Without this,
    hosted image providers (Flux via Pollinations/Cloudflare) generate a
    new face per shot even for the same character -- these are freeze-
    seeded but the model interprets a fresh prompt each time. Prepending
    the character name(s) is the cheapest anchor a text-only prompt
    supports."""
    return ", ".join(_dominant_character_names(scenes, limit))


def _character_seeds(scenes: Sequence, namespace: str, limit: int = 3) -> dict[str, int]:
    """A stable image seed per recurring character (keyed by casefolded name).
    Scenes sharing a protagonist reuse that seed so the SAME character keeps a
    consistent face across shots -- the prompt still varies per scene, so the
    seed anchors identity without freezing composition. See character_visual.py
    for the wider consistency mechanism this is the cheapest slice of."""
    from kronara.character_visual import derive_seed

    return {
        name.casefold(): derive_seed(namespace, name)
        for name in _dominant_character_names(scenes, limit)
    }


def _scene_character_seed(scene, character_seeds: dict[str, int]) -> int | None:
    """The stable seed for this scene's primary recurring character, if any --
    the first of the scene's characters that is a dominant character."""
    for name in getattr(scene, "characters", ()) or ():
        seed = character_seeds.get(str(name).strip().casefold())
        if seed is not None:
            return seed
    return None


def render_graphic_overlay_card(text: str, output_path: str, *, width: int, height: int) -> None:
    """Create a cinematic evidence card, not a blank white document.

    Graphic overlays are deliberately Pillow-drawn because diffusion models
    are unreliable at rendering legible text. The card still belongs to the
    visual language of the episode: dark palette, purple accent, readable
    hierarchy and a restrained waveform instead of a full-frame transcript.
    """
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height))
    pixels = image.load()
    top = (7, 12, 27)
    bottom = (38, 14, 60)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(top[channel] * (1 - ratio) + bottom[channel] * ratio) for channel in range(3))
        for x in range(width):
            pixels[x, y] = color

    draw = ImageDraw.Draw(image)
    margin = int(width * 0.08)
    card = [margin, int(height * 0.18), width - margin, int(height * 0.78)]
    draw.rounded_rectangle(card, radius=28, fill=(10, 18, 38), outline=(126, 74, 238), width=4)
    draw.rounded_rectangle(
        [card[0] + 22, card[1] + 22, card[2] - 22, card[1] + 82],
        radius=18,
        fill=(40, 22, 75),
    )

    def font(size: int):
        for candidate in ("C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

    draw.text((card[0] + 52, card[1] + 38), "EVIDENCIA DE AUDIO", font=font(28), fill=(232, 218, 255))
    draw.text((card[0] + 52, card[1] + 116), "Grabación recuperada · 00:03", font=font(24), fill=(145, 155, 187))

    wrapped = _wrap_text(" ".join(text.split()), max_chars=36)
    line_height = 54
    start_y = card[1] + 240
    for index, line in enumerate(wrapped[:12]):
        draw.text((card[0] + 52, start_y + index * line_height), line, font=font(34), fill=(245, 246, 252))

    waveform_y = card[3] - 120
    waveform = [18, 36, 26, 56, 30, 70, 38, 48, 24, 64, 34, 52, 20, 44, 28, 58, 22, 40, 30, 48]
    bar_width = max(8, int((card[2] - card[0] - 104) / len(waveform)))
    for index, bar in enumerate(waveform):
        x = card[0] + 52 + index * bar_width
        draw.rounded_rectangle(
            [x, waveform_y - bar, x + max(4, bar_width - 8), waveform_y + bar],
            radius=4,
            fill=(167, 92, 255),
        )
    draw.text((margin, int(height * 0.86)), "KRONARA · RECREACIÓN VISUAL LOCAL", font=font(22), fill=(214, 198, 231))
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
    episode_context: str = "",
    scene_index: int = 0,
    total_scenes: int = 0,
    reference_image_path: str | None = None,
    character_seed: int | None = None,
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
    prompt, negative = build_shot_prompt(
        scene.narration,
        negative_prompt,
        visual_style,
        episode_context=episode_context,
        scene_position=f"scene {scene_index}/{total_scenes}" if scene_index and total_scenes else "",
    )
    request = ImageGenerationRequest(
        prompt=prompt, negative_prompt=negative,
        # Stable per-character seed anchors identity across scenes; falls back
        # to the per-scene seed when the scene has no recurring protagonist.
        seed=character_seed if character_seed is not None else _seed_for_shot(scene.scene_id),
        quality_tier=tier,
        reference_image_path=reference_image_path,
        reference_strength=0.45,
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
    episode_context: str = "",
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
    prompt, negative = build_shot_prompt(
        cover_text,
        negative_prompt,
        visual_style,
        episode_context=episode_context,
        scene_position="premium episode cover / reusable thumbnail",
    )
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
    character_descriptions: "dict[str, str] | None" = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> VisualProductionResult:
    if len(voice_duration.per_scene_ms) != len(scenes):
        raise ValueError("voice_duration must have exactly one entry per scene")
    if any(not ref for ref in voice_duration.audio_refs):
        raise ValueError(
            "real per-scene narration audio is required to produce video "
            "(use a voice provider that writes audio_dir, e.g. VoiceBoxVoiceProvider)"
        )

    os.makedirs(output_dir, exist_ok=True)

    def progress(stage: str, detail: str, **extra) -> None:
        if progress_callback is not None:
            progress_callback({"stage": stage, "detail": detail, **extra})

    effective_cover_text = cover_text.strip() or (scenes[0].narration if scenes else episode_id)
    episode_visual_context = _episode_visual_context(
        scenes, visual_style, character_descriptions=character_descriptions
    )
    cover_image_path = os.path.join(output_dir, f"{episode_id}_cover.png")
    try:
        progress("cover", "Generando portada obligatoria del episodio.")
        cover_image_path = generate_cover_image(
            cover_text=effective_cover_text, output_dir=output_dir, episode_id=episode_id,
            image_provider=image_provider, visual_style=visual_style,
            negative_prompt=negative_prompt, episode_context=episode_visual_context,
        )
    except Exception as error:
        progress(
            "cover_fallback",
            "La portada AI falló; creando miniatura gráfica local de respaldo.",
            error=type(error).__name__,
        )
        render_graphic_overlay_card(
            effective_cover_text,
            cover_image_path,
            width=SDXL_BUCKET_9x16[0],
            height=SDXL_BUCKET_9x16[1],
        )
    narration_path = os.path.join(output_dir, f"{episode_id}_narration.mp3")
    progress("audio", "Uniendo narraciones por escena.")
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

    total_scenes = len(scenes)
    cover_images = 1
    scene_plan = []
    planned_source_counts = {"ai_image": 0, "video_loop": 0, "graphic_overlay": 0}
    planned_image_counts = {"fast": 0, "premium": 0}
    planned_shot_count = 0
    for index, scene in enumerate(scenes):
        tier = tier_for_scene(index, voice_duration.per_scene_ms)
        assignment = assignments[scene.scene_id]
        planned_source_counts[assignment.source_kind] += 1
        if assignment.source_kind == "ai_image":
            planned_image_counts[tier] += 1
        shots = plan_shots_for_scene(
            scene.scene_id,
            voice_duration.per_scene_ms[index],
            tier,
            [_SENTINEL_ASSET],
            motion_bias=visual_style.motion_bias if visual_style else "standard",
        )
        planned_shot_count += len(shots)
        scene_plan.append(
            {
                "scene_id": scene.scene_id,
                "scene_index": index + 1,
                "tier": tier,
                "source_kind": assignment.source_kind,
                "image_steps": (
                    PREMIUM_STEPS if tier == "premium"
                    else FAST_STEPS
                ) if assignment.source_kind == "ai_image" else 0,
                "shot_count": len(shots),
                "duration_ms": voice_duration.per_scene_ms[index],
            }
        )
    progress(
        "plan",
        (
            f"Plan visual: {cover_images} portada premium obligatoria, {planned_image_counts['premium']} imagen(es) premium "
            f"de escena, {planned_image_counts['fast']} imagen(es) rápidas, "
            f"{planned_source_counts['graphic_overlay']} overlay(s), {planned_source_counts['video_loop']} video-loop(s), "
            f"{planned_shot_count} toma(s)."
        ),
        ordered_by="visual_director+visual_composer",
        cover_images=cover_images,
        cover_steps=PREMIUM_STEPS if cover_images else 0,
        scene_count=total_scenes,
        total_diffusion_batches=cover_images + planned_image_counts["premium"] + planned_image_counts["fast"],
        total_diffusion_steps=(cover_images + planned_image_counts["premium"]) * PREMIUM_STEPS + planned_image_counts["fast"] * FAST_STEPS,
        planned_image_counts=planned_image_counts,
        planned_source_counts=planned_source_counts,
        planned_shot_count=planned_shot_count,
        scene_plan=scene_plan,
        episode_visual_context=episode_visual_context,
    )

    all_shots: list[Shot] = []
    source_counts = {"ai_image": 0, "video_loop": 0, "graphic_overlay": 0}
    motion_bias = visual_style.motion_bias if visual_style else "standard"
    # Stable seed per recurring character so the same protagonist keeps a
    # consistent face across scenes (keyed by episode so it's deterministic).
    character_seeds = _character_seeds(scenes, episode_id)
    for index, scene in enumerate(scenes):
        tier = tier_for_scene(index, voice_duration.per_scene_ms)
        assignment = assignments[scene.scene_id]
        source_counts[assignment.source_kind] += 1
        progress(
            "scene_asset",
            f"Generando visual {index + 1}/{total_scenes}.",
            current=index + 1,
            total=total_scenes,
            source_kind=assignment.source_kind,
            tier=tier,
            scene_id=scene.scene_id,
            episode_visual_context=episode_visual_context,
            reference_image_path=cover_image_path if assignment.source_kind == "ai_image" else "",
        )
        asset = _resolve_scene_asset(
            scene=scene, assignment=assignment, tier=tier, output_dir=output_dir,
            image_provider=image_provider, visual_style=visual_style,
            negative_prompt=negative_prompt,
            episode_context=episode_visual_context,
            scene_index=index + 1,
            total_scenes=total_scenes,
            reference_image_path=cover_image_path if Path(cover_image_path).exists() else None,
            character_seed=_scene_character_seed(scene, character_seeds),
        )
        all_shots.extend(
            plan_shots_for_scene(
                scene.scene_id, voice_duration.per_scene_ms[index], tier, [asset],
                motion_bias=motion_bias,
            )
        )

    plan = build_visual_track_plan(all_shots, crossfade_ms=crossfade_ms)

    srt_path = os.path.join(output_dir, f"{episode_id}.srt")
    # The player also appears in a narrow inspector panel; keep caption lines
    # short enough to remain legible there as well as in fullscreen playback.
    cues = cues_from_word_boundaries(voice_duration.word_boundaries, max_chars=28)
    Path(srt_path).write_text(build_srt(cues), encoding="utf-8")

    sfx_cues = match_sfx_cues(voice_duration.word_boundaries, keyword_map=DEFAULT_KEYWORD_SFX)
    sfx_paths = (
        sfx_paths_from_library(library, {cue.tag for cue in sfx_cues}) if library is not None else {}
    )
    sfx_tags = tuple(dict.fromkeys(cue.tag for cue in sfx_cues))
    missing_sfx_tags = tuple(tag for tag in sfx_tags if tag not in sfx_paths)
    progress("plan", f"Plan visual listo: {len(plan.shots)} tomas.")

    music_path = None
    if library is not None and visual_style is not None and visual_style.music_moods:
        music_asset = select_music_track(library, visual_style.music_moods)
        music_path = music_asset.file_path if music_asset else None

    raw_output_path = os.path.join(output_dir, f"{episode_id}_raw.mp4")
    progress("render", "Renderizando video vertical con FFmpeg.")
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
    progress("loudness", "Normalizando volumen del episodio.")
    loudness = renderer.normalize_loudness(raw_output_path, output_path)
    progress("qc", "Revisando formato, audio, duración y cuadros negros.")
    qc = renderer.qc(output_path, preset, max_black_seconds=0.5, loudness_range_lufs=(-19.0, -13.0))
    progress("completed", "Producción visual completada.", qc_passed=qc.passed)

    return VisualProductionResult(
        output_path=output_path,
        qc=qc,
        loudness=loudness,
        scene_count=len(scenes),
        shot_count=len(plan.shots),
        source_kind_counts=source_counts,
        cover_image_path=cover_image_path,
        music_path=music_path or "",
        sfx_cue_tags=sfx_tags,
        sfx_resolved_paths=dict(sfx_paths),
        sfx_missing_tags=missing_sfx_tags,
    )
