"""Shot planning + Ken Burns/parallax animation filter construction.

Turns a story's scenes into a sequence of animated "shots" — each an image or
clip held 3-7s with a pan/zoom — and assigns each shot a quality tier. The
premium tier (hook, revelation, climax, emotional close) is decided by
**cumulative time position** against ``narrative_workflow.STAGES``, not by
matching ``StoryScene.purpose``: in production that field is free LLM text
(``routed_story_provider.py`` writes it straight from a completion) and never
coincides with the STAGES slugs, so any design that string-matches it silently
never fires.

FFmpeg's zoompan/xfade offsets are computed here in Python and injected as
literal numbers — never as a running expression inside ffmpeg, which is the
classic source of Ken-Burns/crossfade desync bugs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from kronara import narrative_workflow

_PREMIUM_STAGES = frozenset({"hook", "revelation", "climax", "emotional_close"})

MIN_SHOT_MS = 3000
MAX_SHOT_MS = 7000
DEFAULT_CROSSFADE_MS = 400


@dataclass(frozen=True)
class VisualAsset:
    asset_id: str
    kind: str  # "ai_image" | "video_loop" | "graphic_overlay" | "placeholder"
    path: str
    width: int
    height: int


@dataclass(frozen=True)
class Shot:
    shot_id: str
    scene_id: str
    asset: VisualAsset
    duration_ms: int  # effective screen time; sum over a track == total duration
    tier: str  # "fast" | "premium"
    zoom_start: float
    zoom_end: float
    pan: str  # "left_right" | "right_left" | "top_bottom" | "diagonal" | "center_in"

    def __post_init__(self) -> None:
        if self.duration_ms <= 0:
            raise ValueError("shot duration must be positive")
        if self.tier not in {"fast", "premium"}:
            raise ValueError(f"unknown tier: {self.tier}")


@dataclass(frozen=True)
class VisualTrackPlan:
    shots: tuple[Shot, ...]
    total_duration_ms: int
    crossfade_ms: int

    def __post_init__(self) -> None:
        total = sum(shot.duration_ms for shot in self.shots)
        if self.shots and total != self.total_duration_ms:
            raise ValueError(
                f"shot durations sum to {total}ms, expected {self.total_duration_ms}ms"
            )


def stage_for_offset(
    offset_ms: int, total_ms: int, stages: Sequence[tuple[str, int]] = narrative_workflow.STAGES
) -> str:
    """Which STAGES bucket a timeline offset falls in, by cumulative percentage."""
    if total_ms <= 0:
        return stages[0][0]
    consumed_pct = 0.0
    target_pct = 100.0 * offset_ms / total_ms
    for name, pct in stages:
        consumed_pct += pct
        if target_pct <= consumed_pct:
            return name
    return stages[-1][0]


def tier_for_scene(
    scene_index: int,
    per_scene_ms: Sequence[int],
    *,
    is_last_scene: bool | None = None,
) -> str:
    """"premium" for hook/revelation/climax/emotional_close (by the scene's
    midpoint position) or the final scene (independent of stage math);
    "fast" for everything else."""
    if not per_scene_ms:
        raise ValueError("per_scene_ms must be non-empty")
    if is_last_scene is None:
        is_last_scene = scene_index == len(per_scene_ms) - 1
    if is_last_scene:
        return "premium"
    total = sum(per_scene_ms)
    midpoint = sum(per_scene_ms[:scene_index]) + per_scene_ms[scene_index] // 2
    return "premium" if stage_for_offset(midpoint, total) in _PREMIUM_STAGES else "fast"


def plan_shots_for_scene(
    scene_id: str,
    duration_ms: int,
    tier: str,
    assets: Sequence[VisualAsset],
    *,
    min_shot_ms: int = MIN_SHOT_MS,
    max_shot_ms: int = MAX_SHOT_MS,
) -> tuple[Shot, ...]:
    """Split a scene's duration into 3-7s shots, cycling through the given
    assets. A scene shorter than max_shot_ms becomes exactly one shot (short
    scenes are allowed below the floor; the 3-7s rule governs how a *longer*
    scene is subdivided, not a hard per-shot minimum)."""
    if duration_ms <= 0:
        raise ValueError("scene duration must be positive")
    if not assets:
        raise ValueError("at least one visual asset is required")
    shot_count = max(1, -(-duration_ms // max_shot_ms))  # ceil division
    # Avoid a trailing sliver under min_shot_ms by folding it into one fewer shot.
    if shot_count > 1 and duration_ms // shot_count < min_shot_ms:
        shot_count -= 1
    base = duration_ms // shot_count
    remainder = duration_ms - base * shot_count
    shots: list[Shot] = []
    for index in range(shot_count):
        shot_duration = base + (remainder if index == shot_count - 1 else 0)
        asset = assets[index % len(assets)]
        zoom_start, zoom_end, pan = _motion_for_tier(tier, index)
        shots.append(
            Shot(
                shot_id=f"{scene_id}_shot_{index + 1}",
                scene_id=scene_id,
                asset=asset,
                duration_ms=shot_duration,
                tier=tier,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                pan=pan,
            )
        )
    return tuple(shots)


def _motion_for_tier(tier: str, index: int) -> tuple[float, float, str]:
    if tier == "premium":
        zoom_end = 1.22
        pans = ("diagonal", "left_right", "right_left", "top_bottom")
    else:
        zoom_end = 1.14
        pans = ("center_in", "left_right", "right_left")
    return 1.0, zoom_end, pans[index % len(pans)]


def build_visual_track_plan(
    shots: Sequence[Shot], *, crossfade_ms: int = DEFAULT_CROSSFADE_MS
) -> VisualTrackPlan:
    total = sum(shot.duration_ms for shot in shots)
    return VisualTrackPlan(shots=tuple(shots), total_duration_ms=total, crossfade_ms=crossfade_ms)


def generated_source_ms(plan: VisualTrackPlan, index: int) -> int:
    """Source clip length (ms) to generate for shot `index` via zoompan — every
    shot except the last needs +crossfade_ms of extra footage so the following
    xfade has material to blend from; the last shot needs no trailing pad since
    nothing blends after it. This is what keeps sum(shot.duration_ms) exactly
    equal to the assembled track length despite each xfade consuming overlap."""
    shot = plan.shots[index]
    is_last = index == len(plan.shots) - 1
    return shot.duration_ms + (0 if is_last else plan.crossfade_ms)


def crossfade_offsets_ms(plan: VisualTrackPlan) -> tuple[int, ...]:
    """Cumulative offset (ms, from track start) at which each xfade transition
    begins — one entry per internal join (len(shots)-1 total). Using the
    cumulative EFFECTIVE (not generated) durations as offsets is what makes the
    assembled output land at exactly total_duration_ms; see generated_source_ms."""
    offsets: list[int] = []
    running = 0
    for shot in plan.shots[:-1]:
        running += shot.duration_ms
        offsets.append(running)
    return tuple(offsets)


def zoompan_filter(
    shot: Shot,
    *,
    label_in: str,
    label_out: str,
    preset_width: int,
    preset_height: int,
    fps: int,
    source_ms: int,
) -> str:
    """One scale+zoompan+format stage for a single shot's source clip.
    `source_ms` is the GENERATED length (see generated_source_ms), not the
    shot's effective screen duration."""
    frames = max(1, round(source_ms / 1000 * fps))
    zoom_step = (shot.zoom_end - shot.zoom_start) / frames
    zoom_expr = f"min(zoom+{zoom_step:.6f},{shot.zoom_end:.4f})"
    x_expr, y_expr = _pan_expressions(shot.pan, frames)
    return (
        f"[{label_in}]scale=3840:-1:flags=lanczos,"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={frames}:"
        f"s={preset_width}x{preset_height}:fps={fps},"
        f"format=yuv420p,setsar=1[{label_out}]"
    )


def _pan_expressions(pan: str, frames: int) -> tuple[str, str]:
    center_y = "ih/2-(ih/zoom/2)"
    center_x = "iw/2-(iw/zoom/2)"
    if pan == "left_right":
        return f"(iw-iw/zoom)*(on/{frames})", center_y
    if pan == "right_left":
        return f"(iw-iw/zoom)*(1-on/{frames})", center_y
    if pan == "top_bottom":
        return center_x, f"(ih-ih/zoom)*(on/{frames})"
    if pan == "diagonal":
        return f"(iw-iw/zoom)*(on/{frames})", f"(ih-ih/zoom)*(on/{frames})*0.4"
    return center_x, center_y  # center_in / unknown -> centered zoom


def xfade_chain(plan: VisualTrackPlan, shot_labels: Sequence[str]) -> tuple[str, ...]:
    """Chain of xfade filter lines joining consecutive shot streams; one line
    per transition, with exact numeric offsets computed in Python (never a
    running ffmpeg expression)."""
    if len(shot_labels) != len(plan.shots):
        raise ValueError("one label is required per shot")
    offsets = crossfade_offsets_ms(plan)
    if not offsets:
        return ()
    lines: list[str] = []
    current = shot_labels[0]
    for index, offset_ms in enumerate(offsets):
        next_label = shot_labels[index + 1]
        out_label = f"vx{index + 1}" if index < len(offsets) - 1 else "vout"
        duration_s = plan.crossfade_ms / 1000
        offset_s = offset_ms / 1000
        lines.append(
            f"[{current}][{next_label}]xfade=transition=fade:"
            f"duration={duration_s:.3f}:offset={offset_s:.3f}[{out_label}]"
        )
        current = out_label
    return tuple(lines)
