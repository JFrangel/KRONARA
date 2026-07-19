"""Voice synthesis and real-duration measurement.

Kronara used to *estimate* narration length as ``words / 2.5``. That is fine for a
first pass but drifts from what the ear actually hears. This module measures the
**real** duration by synthesizing each scene with a neural voice (Microsoft Edge
neural voices via the ``voice.synthesize`` authority tool) and reading the
returned audio duration and per-word timings.

The effect is governed by Rust (``voice.synthesize`` is on the authority
allowlist); Python only asks for it. When the tool is unavailable the measurer
degrades explicitly to the word-rate estimate so the pipeline still runs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass(frozen=True)
class VoiceProfile:
    voice_id: str
    locale: str
    gender: str
    provider: str
    production_stable: bool


DEFAULT_VOICES = (
    VoiceProfile("es-BO-MarceloNeural", "es-BO", "male", "edge", True),
    VoiceProfile("es-CL-LorenzoNeural", "es-CL", "male", "edge", True),
    VoiceProfile("es-BO-SofiaNeural", "es-BO", "female", "edge", True),
    VoiceProfile("es-CO-GonzaloNeural", "es-CO", "male", "edge", True),
    VoiceProfile("es-CO-SalomeNeural", "es-CO", "female", "edge", True),
)


class VoiceRegistry:
    def __init__(self, voices: Iterable[VoiceProfile]):
        self._voices = {voice.voice_id: voice for voice in voices}

    def get(self, voice_id: str) -> VoiceProfile:
        try:
            return self._voices[voice_id]
        except KeyError as error:
            raise LookupError(voice_id) from error


@dataclass(frozen=True)
class WordBoundary:
    word: str
    offset_ms: int
    duration_ms: int


@dataclass(frozen=True)
class VoiceSynthesisRequest:
    text: str
    voice_id: str
    rate: float = 0.0
    pitch: float = 0.0

    def cache_key(self) -> str:
        payload = f"{self.voice_id}|{self.rate}|{self.pitch}|{self.text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceSynthesisResult:
    voice_id: str
    duration_ms: int
    audio_ref: str | None = None
    word_boundaries: tuple[WordBoundary, ...] = ()
    cached: bool = False
    degraded: bool = False


class VoiceSynthesisProvider(Protocol):
    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult: ...


class AuthorityVoiceProvider:
    """Calls the Rust-governed ``voice.synthesize`` tool and caches by content hash."""

    def __init__(self, authority, *, cache: dict[str, VoiceSynthesisResult] | None = None):
        self.authority = authority
        self._cache = cache if cache is not None else {}

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        key = request.cache_key()
        if key in self._cache:
            cached = self._cache[key]
            return VoiceSynthesisResult(
                voice_id=cached.voice_id,
                duration_ms=cached.duration_ms,
                audio_ref=cached.audio_ref,
                word_boundaries=cached.word_boundaries,
                cached=True,
                degraded=cached.degraded,
            )
        payload = self.authority.invoke(
            "voice.synthesize",
            {
                "text": request.text,
                "voice_id": request.voice_id,
                "rate": request.rate,
                "pitch": request.pitch,
            },
        )
        result = VoiceSynthesisResult(
            voice_id=str(payload.get("voice_id", request.voice_id)),
            duration_ms=int(payload["duration_ms"]),
            audio_ref=payload.get("audio_ref"),
            word_boundaries=tuple(
                WordBoundary(
                    word=str(item["word"]),
                    offset_ms=int(item["offset_ms"]),
                    duration_ms=int(item["duration_ms"]),
                )
                for item in payload.get("word_boundaries", ())
            ),
        )
        self._cache[key] = result
        return result


class EstimatingVoiceProvider:
    """No-network fallback: duration from a spoken words-per-minute rate."""

    def __init__(self, words_per_minute: float = 150.0):
        self.words_per_minute = words_per_minute

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        words = len(request.text.split())
        duration_ms = int(round(words / self.words_per_minute * 60_000))
        return VoiceSynthesisResult(
            voice_id=request.voice_id, duration_ms=duration_ms, degraded=True
        )


@dataclass(frozen=True)
class MeasuredDuration:
    total_seconds: float
    per_scene_ms: tuple[int, ...]
    word_boundaries: tuple[WordBoundary, ...] = field(default_factory=tuple)
    degraded: bool = False


class SceneDurationMeasurer:
    """Measures real narration duration scene-by-scene via a voice provider.

    Implements the ``DurationMeasurer`` shape the StoryEngine expects: given the
    scenes, return the summed measured duration (in seconds) plus per-scene
    milliseconds and word timings (usable later for subtitles).
    """

    def __init__(self, provider: VoiceSynthesisProvider, *, voice_id: str, rate: float = 0.0, pitch: float = 0.0):
        self.provider = provider
        self.voice_id = voice_id
        self.rate = rate
        self.pitch = pitch

    def measure(self, scenes) -> MeasuredDuration:
        per_scene: list[int] = []
        boundaries: list[WordBoundary] = []
        degraded = False
        offset = 0
        for scene in scenes:
            text = getattr(scene, "narration", "") or ""
            result = self.provider.synthesize(
                VoiceSynthesisRequest(text=text, voice_id=self.voice_id, rate=self.rate, pitch=self.pitch)
            )
            per_scene.append(result.duration_ms)
            degraded = degraded or result.degraded
            for boundary in result.word_boundaries:
                boundaries.append(
                    WordBoundary(boundary.word, offset + boundary.offset_ms, boundary.duration_ms)
                )
            offset += result.duration_ms
        total_ms = sum(per_scene)
        return MeasuredDuration(
            total_seconds=total_ms / 1000.0,
            per_scene_ms=tuple(per_scene),
            word_boundaries=tuple(boundaries),
            degraded=degraded,
        )
