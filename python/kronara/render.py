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
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderPreset:
    name: str
    width: int
    height: int
    fps: int


REEL_9x16 = RenderPreset("reel_9x16", 1080, 1920, 30)
MASTER_16x9 = RenderPreset("master_16x9", 1920, 1080, 30)
PRESETS = {preset.name: preset for preset in (REEL_9x16, MASTER_16x9)}


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


@dataclass(frozen=True)
class RenderResult:
    output_path: str
    preset: str
    qc: QCReport


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
        args += ["-vf", f"subtitles='{escaped}'"]
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

    def qc(self, path: str, preset: RenderPreset) -> QCReport:
        data = self.probe(path)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        width = int(video.get("width", 0))
        height = int(video.get("height", 0))
        duration = float(data.get("format", {}).get("duration", 0.0))
        issues: list[str] = []
        if (width, height) != (preset.width, preset.height):
            issues.append("resolution_mismatch")
        if not has_audio:
            issues.append("missing_audio")
        if duration <= 0:
            issues.append("zero_duration")
        return QCReport(
            width=width,
            height=height,
            duration_seconds=duration,
            has_audio=has_audio,
            passed=not issues,
            issues=tuple(issues),
        )
