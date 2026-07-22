"""Video rendering over FFmpeg.

Turns a narration audio track (from :mod:`kronara.voice`) plus a background and
optional burned subtitles into a real MP4 — a vertical Reel (9:16) or a
horizontal master (16:9). FFmpeg is invoked with argument lists built in code
(no shell interpolation) and the output is QC'd with ffprobe.

Like voice synthesis, rendering is a secret-free effect; the binary is located
via ``KRONARA_FFMPEG`` / PATH and the caller degrades explicitly when it is
absent.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from kronara.audio_mix import DuckingEnvelope, SfxCue, build_mix_filters
from kronara.composition import (
    VisualTrackPlan,
    generated_source_ms,
    video_clip_filter,
    xfade_chain,
    zoompan_filter,
)


@dataclass(frozen=True)
class RenderPreset:
    name: str
    width: int
    height: int
    fps: int


REEL_9x16 = RenderPreset("reel_9x16", 1080, 1920, 30)
MASTER_16x9 = RenderPreset("master_16x9", 1920, 1080, 30)
PRESETS = {preset.name: preset for preset in (REEL_9x16, MASTER_16x9)}
SUBTITLE_STYLE = (
    "FontName=Arial,FontSize=10,PrimaryColour=&H00FFFFFF&,"
    "OutlineColour=&HCC000000&,BorderStyle=1,Outline=2,Shadow=1,"
    "Alignment=2,MarginV=90,WrapStyle=2"
)


@dataclass(frozen=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class QCReport:
    width: int
    height: int
    duration_seconds: float
    has_audio: bool
    passed: bool
    issues: tuple[str, ...] = ()
    black_seconds: float = 0.0
    integrated_lufs: float | None = None


@dataclass(frozen=True)
class LoudnessReport:
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range: float


@dataclass(frozen=True)
class RenderResult:
    output_path: str
    preset: str
    qc: QCReport


def _parse_loudnorm_json(stderr_text: str) -> dict:
    """ffmpeg's loudnorm filter writes a JSON block to stderr, not stdout."""
    start = stderr_text.rfind("{")
    end = stderr_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("loudnorm did not report measurement JSON")
    return json.loads(stderr_text[start : end + 1])


def find_ffmpeg(kind: str = "ffmpeg") -> str | None:
    """Locate ffmpeg/ffprobe via KRONARA_FFMPEG(_DIR) or PATH."""
    import os

    override = os.environ.get(f"KRONARA_{kind.upper()}")
    if override and Path(override).exists():
        return override
    directory = os.environ.get("KRONARA_FFMPEG_DIR")
    if directory:
        candidate = Path(directory) / f"{kind}.exe"
        if candidate.exists():
            return str(candidate)
        candidate = Path(directory) / kind
        if candidate.exists():
            return str(candidate)
    return shutil.which(kind)


def _ms_to_srt(ms: int) -> str:
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_srt(cues: tuple[SubtitleCue, ...]) -> str:
    """Build an SRT subtitle document from timed cues."""
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n{_ms_to_srt(cue.start_ms)} --> {_ms_to_srt(cue.end_ms)}\n{cue.text.strip()}\n"
        )
    return "\n".join(blocks)


def cues_from_word_boundaries(boundaries, *, max_chars: int = 42) -> tuple[SubtitleCue, ...]:
    """Group per-word timings into short, readable subtitle lines."""
    cues: list[SubtitleCue] = []
    line: list = []
    start = None
    length = 0
    for boundary in boundaries:
        word = getattr(boundary, "word", "")
        offset = getattr(boundary, "offset_ms", 0)
        duration = getattr(boundary, "duration_ms", 0)
        if start is None:
            start = offset
        if length + len(word) + 1 > max_chars and line:
            cues.append(SubtitleCue(start, offset, " ".join(line)))
            line = []
            length = 0
            start = offset
        line.append(word)
        length += len(word) + 1
        end = offset + duration
    if line and start is not None:
        cues.append(SubtitleCue(start, end, " ".join(line)))
    return tuple(cues)


def build_render_args(
    ffmpeg: str,
    *,
    audio_path: str,
    output_path: str,
    preset: RenderPreset,
    background_color: str = "black",
    subtitle_path: str | None = None,
) -> list[str]:
    """Construct the ffmpeg argument list (no shell). Background color + audio,
    optionally burning an SRT subtitle track."""
    args = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={background_color}:s={preset.width}x{preset.height}:r={preset.fps}",
        "-i",
        audio_path,
    ]
    if subtitle_path:
        escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")
        args += ["-vf", f"subtitles='{escaped}':force_style='{SUBTITLE_STYLE}'"]
    args += [
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        output_path,
    ]
    return args


def build_composition_args(
    ffmpeg: str,
    *,
    visual_plan: VisualTrackPlan,
    narration_path: str,
    narration_duration_ms: int,
    output_path: str,
    preset: RenderPreset,
    music_path: str | None = None,
    sfx_cues: Sequence[SfxCue] = (),
    sfx_paths: Mapping[str, str] | None = None,
    subtitle_path: str | None = None,
    music_duck_gain: float = 0.1,
) -> list[str]:
    """Construct the full composition ffmpeg argument list: sequenced Ken-Burns
    shots (with crossfades) as the video track, narration + optionally-ducked
    music + timed low-volume SFX as the audio track, optional burned subtitles.

    One ``-loop 1 -i <image>`` input per shot, one audio input per unique SFX
    tag actually used (a tag can be referenced by more than one cue — ffmpeg
    lets a filter_complex read the same input label into multiple filter
    chains, so this never needs a duplicate input for a repeated tag)."""
    sfx_paths = sfx_paths or {}
    args: list[str] = [ffmpeg, "-y", "-i", narration_path]
    narration_input = "0:a"
    next_index = 1

    music_input: str | None = None
    if music_path:
        args += ["-i", music_path]
        music_input = f"{next_index}:a"
        next_index += 1

    used_tags = sorted({cue.tag for cue in sfx_cues} & set(sfx_paths))
    sfx_input_labels: dict[str, str] = {}
    for tag in used_tags:
        args += ["-i", sfx_paths[tag]]
        sfx_input_labels[tag] = f"{next_index}:a"
        next_index += 1

    visual_input_start = next_index
    for shot in visual_plan.shots:
        if shot.asset.kind == "video_loop":
            # Loop indefinitely so a clip shorter than the shot's generated
            # source length still fills it; the per-shot filter trims down
            # to the exact length needed, never pads.
            args += ["-stream_loop", "-1", "-i", shot.asset.path]
        else:
            args += ["-loop", "1", "-i", shot.asset.path]
        next_index += 1

    filter_lines: list[str] = []
    shot_labels = [f"v{i}" for i in range(len(visual_plan.shots))]
    for index, shot in enumerate(visual_plan.shots):
        source_ms = generated_source_ms(visual_plan, index)
        label_in = f"{visual_input_start + index}:v"
        common = dict(
            label_in=label_in,
            label_out=shot_labels[index],
            preset_width=preset.width,
            preset_height=preset.height,
            fps=preset.fps,
            source_ms=source_ms,
        )
        if shot.asset.kind == "video_loop":
            filter_lines.append(video_clip_filter(shot, **common))
        else:
            filter_lines.append(zoompan_filter(shot, **common))
    xfade_lines = xfade_chain(visual_plan, shot_labels)
    filter_lines.extend(xfade_lines)
    video_label = "vout" if xfade_lines else shot_labels[0]

    if subtitle_path:
        escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")
        filter_lines.append(
            f"[{video_label}]subtitles='{escaped}':force_style='{SUBTITLE_STYLE}'[vsub]"
        )
        video_label = "vsub"

    if music_input:
        envelope = DuckingEnvelope(
            narration_start_s=0.0,
            narration_end_s=narration_duration_ms / 1000,
            duck_gain=music_duck_gain,
        )
        filter_lines.extend(
            build_mix_filters(
                music_envelope=envelope,
                sfx_cues=sfx_cues,
                sfx_input_labels=sfx_input_labels,
                narration_input=narration_input,
                music_input=music_input,
                output_label="mix",
            )
        )
        audio_map = "[mix]"
    else:
        audio_map = f"{narration_input}"  # raw stream selector, no brackets

    args += ["-filter_complex", ";".join(filter_lines)]
    args += ["-map", f"[{video_label}]", "-map", audio_map]
    args += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-t", f"{narration_duration_ms / 1000:.3f}",
        output_path,
    ]
    return args


class FfmpegRenderer:
    def __init__(self, ffmpeg: str | None = None, ffprobe: str | None = None):
        self.ffmpeg = ffmpeg or find_ffmpeg("ffmpeg")
        self.ffprobe = ffprobe or find_ffmpeg("ffprobe")
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg binary not found (set KRONARA_FFMPEG)")

    def render(
        self,
        *,
        audio_path: str,
        output_path: str,
        preset: RenderPreset,
        background_color: str = "black",
        subtitle_path: str | None = None,
        timeout: int = 300,
    ) -> RenderResult:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        args = build_render_args(
            self.ffmpeg,
            audio_path=audio_path,
            output_path=output_path,
            preset=preset,
            background_color=background_color,
            subtitle_path=subtitle_path,
        )
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg render failed: {completed.stderr[-500:]}")
        qc = self.qc(output_path, preset)
        return RenderResult(output_path=output_path, preset=preset.name, qc=qc)

    def render_composition(
        self,
        *,
        visual_plan: VisualTrackPlan,
        narration_path: str,
        narration_duration_ms: int,
        output_path: str,
        preset: RenderPreset,
        music_path: str | None = None,
        sfx_cues: Sequence[SfxCue] = (),
        sfx_paths: Mapping[str, str] | None = None,
        subtitle_path: str | None = None,
        music_duck_gain: float = 0.1,
        timeout: int = 1800,
    ) -> RenderResult:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        args = build_composition_args(
            self.ffmpeg,
            visual_plan=visual_plan,
            narration_path=narration_path,
            narration_duration_ms=narration_duration_ms,
            output_path=output_path,
            preset=preset,
            music_path=music_path,
            sfx_cues=sfx_cues,
            sfx_paths=sfx_paths,
            subtitle_path=subtitle_path,
            music_duck_gain=music_duck_gain,
        )
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg composition render failed: {completed.stderr[-1500:]}")
        qc = self.qc(output_path, preset)
        return RenderResult(output_path=output_path, preset=preset.name, qc=qc)

    def measure_loudness(
        self,
        input_path: str,
        *,
        target_i: float = -16.0,
        target_tp: float = -1.5,
        target_lra: float = 11.0,
        timeout: int = 300,
    ) -> LoudnessReport:
        """Measure-only pass (no correction applied) -- the natural loudness
        of a clip as-is. Distinct from `normalize_loudness`: two clips each
        normalized toward the same target would converge to ~target_i
        regardless of their original relative loudness, which is useless for
        comparing them (e.g. V4's duck_gain calibration: how many LU below
        the narration does the ducked music actually sit)."""
        if not self.ffprobe:
            raise RuntimeError("ffprobe not found")
        measure_filter = (
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
        )
        measure = subprocess.run(
            [self.ffmpeg, "-i", input_path, "-af", measure_filter, "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
        )
        measured = _parse_loudnorm_json(measure.stderr)
        return LoudnessReport(
            integrated_lufs=float(measured["input_i"]),
            true_peak_dbtp=float(measured["input_tp"]),
            loudness_range=float(measured["input_lra"]),
        )

    def normalize_loudness(
        self,
        input_path: str,
        output_path: str,
        *,
        target_i: float = -16.0,
        target_tp: float = -1.5,
        target_lra: float = 11.0,
        timeout: int = 300,
    ) -> LoudnessReport:
        """Two-pass EBU R128 loudness normalization: measure, then apply with
        the measured values so the correction is accurate (single-pass
        loudnorm is measurably less precise). Only the audio stream is
        re-encoded (`-c:v copy`) — the video is not rendered twice."""
        if not self.ffprobe:
            raise RuntimeError("ffprobe not found")
        measure_filter = (
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
        )
        measure = subprocess.run(
            [self.ffmpeg, "-i", input_path, "-af", measure_filter, "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout,
        )
        measured = _parse_loudnorm_json(measure.stderr)
        apply_filter = (
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
            f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            "linear=true:print_format=json"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        apply_run = subprocess.run(
            [
                self.ffmpeg, "-y", "-i", input_path,
                "-af", apply_filter, "-c:v", "copy", output_path,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        if apply_run.returncode != 0:
            raise RuntimeError(f"loudnorm apply pass failed: {apply_run.stderr[-500:]}")
        final = _parse_loudnorm_json(apply_run.stderr)
        return LoudnessReport(
            integrated_lufs=float(final.get("output_i", final["input_i"])),
            true_peak_dbtp=float(final.get("output_tp", final["input_tp"])),
            loudness_range=float(final.get("output_lra", final["input_lra"])),
        )

    def probe(self, path: str) -> dict:
        if not self.ffprobe:
            raise RuntimeError("ffprobe not found")
        args = [
            self.ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            path,
        ]
        completed = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return json.loads(completed.stdout or "{}")

    def qc(
        self,
        path: str,
        preset: RenderPreset,
        *,
        max_black_seconds: float | None = None,
        loudness_range_lufs: tuple[float, float] | None = None,
        timeout: int = 120,
    ) -> QCReport:
        """Both extended checks are opt-in (None skips them) so the two internal
        callers -- ``render()``'s intentional solid-color background and
        ``render_composition()``'s pre-loudnorm pass -- keep their existing,
        already-tested behavior. The production pipeline (V8) requests both
        explicitly on the final file: ``max_black_seconds`` to catch a shot
        that somehow rendered as a black frame despite V1's per-image check,
        ``loudness_range_lufs`` to confirm normalize_loudness() actually took
        (a file QC'd before normalization has no target to compare against)."""
        data = self.probe(path)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        width = int(video.get("width", 0))
        height = int(video.get("height", 0))
        duration = float(data.get("format", {}).get("duration", 0.0))
        black_seconds = self._detect_black(path, timeout=timeout) if max_black_seconds is not None else 0.0
        integrated_lufs = None
        issues: list[str] = []
        if (width, height) != (preset.width, preset.height):
            issues.append("resolution_mismatch")
        if not has_audio:
            issues.append("missing_audio")
        if duration <= 0:
            issues.append("zero_duration")
        if max_black_seconds is not None and black_seconds > max_black_seconds:
            issues.append("black_frames_detected")
        if loudness_range_lufs is not None and has_audio:
            integrated_lufs = self.measure_loudness(path, timeout=timeout).integrated_lufs
            low, high = loudness_range_lufs
            if not (low <= integrated_lufs <= high):
                issues.append("loudness_out_of_range")
        return QCReport(
            width=width,
            height=height,
            duration_seconds=duration,
            has_audio=has_audio,
            passed=not issues,
            issues=tuple(issues),
            black_seconds=black_seconds,
            integrated_lufs=integrated_lufs,
        )

    def _detect_black(self, path: str, *, timeout: int) -> float:
        result = subprocess.run(
            [
                self.ffmpeg, "-i", path,
                "-vf", "blackdetect=d=0.1:pic_th=0.98",
                "-an", "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        return sum(
            float(match) for match in re.findall(r"black_duration:([\d.]+)", result.stderr)
        )
