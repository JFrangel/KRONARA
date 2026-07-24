"""Voice synthesis and real-duration measurement.

Kronara used to *estimate* narration length as ``words / 2.5``. That is fine for a
first pass but drifts from what the ear actually hears. This module measures the
**real** duration by synthesizing each scene with a cloned voice (a self-hosted
**VoiceBox** server, primary as of v0.8 -- see :class:`VoiceBoxVoiceProvider`) and
reading the returned audio's real duration.

When VoiceBox is unavailable the measurer degrades explicitly, via
:class:`FallbackVoiceProvider`, to the word-rate estimate so the pipeline still
runs (silently, without a crash). Older paths could also route synthesis through
the Rust-governed ``voice.synthesize`` authority tool.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

from kronara.speech_rate import DEFAULT_WORDS_PER_SECOND


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


class VoiceBoxVoiceProvider:
    """Real synthesis via a self-hosted **VoiceBox** server
    (github.com/jamiepine/voicebox, MIT). Kronara's primary voice as of v0.8 --
    replaces edge-tts. Clones a voice once (a VoiceBox *profile*) and reuses it
    per program, so narration keeps one consistent identity.

    VoiceBox generates asynchronously: ``POST /generate`` returns a generation id
    immediately, then the audio becomes fetchable at ``GET /audio/{id}`` (404
    while it's still rendering). Duration is measured from the returned audio with
    ffprobe -- the same source of truth the rest of the pipeline uses -- not
    trusted from the API. Secret-free (a local server, default
    ``http://127.0.0.1:17493``); callers treat any error as "degrade to the
    estimate" via :class:`FallbackVoiceProvider`.

    Config (env or constructor): ``KRONARA_VOICEBOX_URL``,
    ``KRONARA_VOICEBOX_PROFILE`` (the cloned voice's profile_id; a per-program
    ``voice_id`` overrides it), ``KRONARA_VOICEBOX_LANGUAGE`` (default ``es``),
    ``KRONARA_VOICEBOX_ENGINE`` (default: VoiceBox's own default, ``qwen``).
    """

    DEFAULT_URL = "http://127.0.0.1:17493"

    def __init__(
        self,
        *,
        base_url: "str | None" = None,
        profile_id: "str | None" = None,
        language: "str | None" = None,
        engine: "str | None" = None,
        audio_dir: "str | None" = None,
        timeout: float = 180.0,
        poll_interval: float = 1.0,
        ffprobe: "str | None" = None,
        settings_path: "str | None" = None,
        opener=None,
    ):
        self.base_url = (
            base_url or os.environ.get("KRONARA_VOICEBOX_URL") or self.DEFAULT_URL
        ).rstrip("/")
        self.profile_id = profile_id or os.environ.get("KRONARA_VOICEBOX_PROFILE") or ""
        self.language = language or os.environ.get("KRONARA_VOICEBOX_LANGUAGE") or "es"
        self.engine = engine or os.environ.get("KRONARA_VOICEBOX_ENGINE") or ""
        self.audio_dir = audio_dir
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._ffprobe = ffprobe
        # Optional voice_settings.v1.json (data_dir) -- read per-synthesis so a
        # speed change in Configuración → Voces applies to the next narration
        # without restarting the sidecar.
        self._settings_path = settings_path
        # Injectable for tests: a callable(url, data, headers, method) -> (status, bytes).
        self._opener = opener or self._urlopen

    def _speed(self) -> float:
        """Playback speed multiplier for narration (1.0 = normal). From the
        voice_settings file when present, else KRONARA_VOICEBOX_SPEED, else 1.0.
        Clamped to ffmpeg atempo's single-filter range."""
        speed = 1.0
        if self._settings_path:
            try:
                import json

                speed = float(
                    json.loads(Path(self._settings_path).read_text(encoding="utf-8")).get(
                        "speed", 1.0
                    )
                )
            except Exception:
                speed = 1.0
        else:
            env = os.environ.get("KRONARA_VOICEBOX_SPEED")
            speed = float(env) if env else 1.0
        return max(0.5, min(2.0, speed))

    def _apply_speed(self, path: str, speed: float) -> None:
        """Time-stretch the narration in place with ffmpeg ``atempo`` (changes
        tempo, preserves pitch). No-op when speed≈1 or ffmpeg is missing."""
        if abs(speed - 1.0) < 0.01:
            return
        from kronara.render import find_ffmpeg

        ffmpeg = find_ffmpeg("ffmpeg")
        if not ffmpeg:
            return
        tmp = f"{path}.spd.wav"
        try:
            completed = subprocess.run(
                [ffmpeg, "-y", "-i", path, "-filter:a", f"atempo={speed:.3f}", tmp],
                capture_output=True, text=True, timeout=90,
            )
            if completed.returncode == 0 and os.path.exists(tmp):
                os.replace(tmp, path)
        except Exception:
            pass

    @staticmethod
    def _urlopen(url, data=None, headers=None, method="GET", timeout=30):
        import urllib.request

        req = urllib.request.Request(
            url, data=data, headers=headers or {}, method=method
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200), response.read()

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        import json
        import time
        import urllib.error

        profile_id = self.profile_id or request.voice_id
        if not profile_id:
            raise RuntimeError(
                "VoiceBox profile_id is required "
                "(set KRONARA_VOICEBOX_PROFILE or a per-program voice_id)"
            )
        body = {"profile_id": profile_id, "text": request.text, "language": self.language}
        if self.engine:
            body["engine"] = self.engine
        try:
            _, created_bytes = self._opener(
                f"{self.base_url}/generate",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            generation_id = str(json.loads(created_bytes.decode("utf-8")).get("id") or "")
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise RuntimeError(f"VoiceBox /generate failed: {type(error).__name__}") from error
        if not generation_id:
            raise RuntimeError("VoiceBox /generate returned no generation id")

        audio = self._poll_audio(generation_id)
        audio_ref = None
        if self.audio_dir and audio:
            os.makedirs(self.audio_dir, exist_ok=True)
            audio_ref = os.path.join(self.audio_dir, f"{request.cache_key()}.wav")
            with open(audio_ref, "wb") as handle:
                handle.write(audio)
            # Apply the configured narration speed BEFORE measuring, so the
            # duration reflects what the video will actually play.
            self._apply_speed(audio_ref, self._speed())
        duration_ms = self._duration_ms(audio_ref) if audio_ref else 0
        if duration_ms <= 0:
            # Never return a zero duration -- fall back to a word-rate estimate so
            # subtitle/SFX timing stays sane even if ffprobe is unavailable.
            duration_ms = int(
                round(len(request.text.split()) / DEFAULT_WORDS_PER_SECOND * 1000)
            )
        return VoiceSynthesisResult(
            voice_id=request.voice_id,
            duration_ms=duration_ms,
            audio_ref=audio_ref,
            degraded=False,
        )

    def _poll_audio(self, generation_id: str) -> bytes:
        import time
        import urllib.error

        url = f"{self.base_url}/audio/{generation_id}"
        elapsed = 0.0
        while elapsed < self.timeout:
            try:
                status, payload = self._opener(url, method="GET")
                if status == 200 and payload:
                    return payload
            except urllib.error.HTTPError as error:
                if error.code != 404:  # 404 == still generating (or failed)
                    raise RuntimeError(
                        f"VoiceBox /audio failed: HTTP {error.code}"
                    ) from error
            except (urllib.error.URLError, OSError) as error:
                raise RuntimeError(f"VoiceBox /audio failed: {type(error).__name__}") from error
            time.sleep(self.poll_interval)
            elapsed += self.poll_interval
        raise RuntimeError("VoiceBox generation timed out")

    def _duration_ms(self, path: str) -> int:
        from kronara.render import find_ffmpeg

        ffprobe = self._ffprobe or find_ffmpeg("ffprobe")
        if not ffprobe:
            return 0
        try:
            completed = subprocess.run(
                [
                    ffprobe, "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                return int(round(float(completed.stdout.strip()) * 1000))
        except Exception:
            return 0
        return 0


def build_multipart(
    fields: dict[str, str], files: dict[str, tuple[str, bytes]]
) -> tuple[str, bytes]:
    """Hand-roll a ``multipart/form-data`` body (Kronara has no ``requests``
    dependency -- everything is stdlib urllib). Returns (boundary, body)."""
    import uuid

    boundary = "----KronaraForm" + uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    for name, (filename, content) in files.items():
        header = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode("utf-8")
        parts.append(header + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, b"".join(parts)


class VoiceBoxError(RuntimeError):
    """A VoiceBox admin call failed with a message worth showing the user
    (e.g. duplicate name, reference audio too short/quiet)."""


class VoiceBoxAdmin:
    """Management calls to a local VoiceBox server: create/list/delete cloned
    voice *profiles* and upload reference *samples* (audio + transcript). Kept
    separate from :class:`VoiceBoxVoiceProvider` (which only synthesizes). The
    ``opener`` is injectable for tests -- same ``(url, data, headers, method,
    timeout) -> (status, bytes)`` contract as the provider, raising
    urllib.error.HTTPError on non-2xx so error bodies can be surfaced.

    Cloning in VoiceBox is a two-step, transcript-required flow: create a
    ``voice_type="cloned"`` profile, then POST one or more reference samples,
    each a short audio clip WITH its exact transcript (``reference_text``). The
    clone materializes lazily at first synthesis."""

    CLONING_ENGINES = ("qwen", "luxtts", "chatterbox", "chatterbox_turbo", "tada")

    def __init__(self, base_url: "str | None" = None, *, opener=None):
        self.base_url = (
            base_url or os.environ.get("KRONARA_VOICEBOX_URL") or "http://127.0.0.1:17493"
        ).rstrip("/")
        self._opener = opener or VoiceBoxVoiceProvider._urlopen

    def _call(self, path, *, data=None, headers=None, method="GET", timeout=30):
        import urllib.error

        try:
            return self._opener(
                f"{self.base_url}{path}", data=data, headers=headers or {}, method=method, timeout=timeout
            )
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                import json

                detail = str(json.loads(error.read().decode("utf-8")).get("detail", ""))
            except Exception:
                detail = ""
            raise VoiceBoxError(detail or f"VoiceBox HTTP {error.code}") from error

    def list_profiles(self) -> list[dict]:
        import json

        _, payload = self._call("/profiles", method="GET", timeout=10)
        data = json.loads(payload.decode("utf-8"))
        return list(data) if isinstance(data, list) else []

    def create_cloned_profile(self, *, name: str, language: str, engine: str) -> dict:
        import json

        body = {
            "name": name,
            "language": language,
            "voice_type": "cloned",
            "default_engine": engine,
        }
        _, payload = self._call(
            "/profiles",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
            timeout=15,
        )
        return json.loads(payload.decode("utf-8"))

    def upload_sample(
        self, profile_id: str, *, audio: bytes, filename: str, reference_text: str
    ) -> None:
        boundary, body = build_multipart(
            {"reference_text": reference_text}, {"file": (filename, audio)}
        )
        self._call(
            f"/profiles/{profile_id}/samples",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
            timeout=120,
        )

    def delete_profile(self, profile_id: str) -> bool:
        import urllib.error

        try:
            self._call(f"/profiles/{profile_id}", method="DELETE", timeout=15)
            return True
        except VoiceBoxError as error:
            if isinstance(error.__cause__, urllib.error.HTTPError) and error.__cause__.code == 404:
                return False
            raise


class EstimatingVoiceProvider:
    """No-network fallback: duration from a spoken words-per-minute rate.

    When a rate_learner is supplied, its per-voice learned words/second
    (from real past measurements -- see SceneDurationMeasurer) is used
    instead of the fixed `words_per_minute` default, so even this degraded
    no-network path reflects reality rather than the original guess.
    """

    def __init__(
        self,
        words_per_minute: float = 150.0,
        *,
        audio_dir: str | None = None,
        rate_learner: "object | None" = None,
    ):
        self.words_per_minute = words_per_minute
        self.audio_dir = audio_dir
        self.rate_learner = rate_learner

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        words = len(request.text.split())
        words_per_second = (
            self.rate_learner.estimate(request.voice_id).words_per_second
            if self.rate_learner is not None
            else self.words_per_minute / 60.0
        )
        duration_ms = int(round(words / words_per_second * 1000))
        audio_ref = None
        if self.audio_dir:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                Path(self.audio_dir).mkdir(parents=True, exist_ok=True)
                audio_ref = os.path.join(self.audio_dir, f"{request.cache_key()}.mp3")
                duration_seconds = max(duration_ms / 1000.0, 0.25)
                completed = subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=r=24000:cl=mono",
                        "-t",
                        f"{duration_seconds:.3f}",
                        "-acodec",
                        "libmp3lame",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        audio_ref,
                    ],
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0 or not Path(audio_ref).exists():
                    audio_ref = None
        return VoiceSynthesisResult(
            voice_id=request.voice_id,
            duration_ms=duration_ms,
            audio_ref=audio_ref,
            degraded=True,
        )


class FallbackVoiceProvider:
    """Tries `primary` (e.g. VoiceBoxVoiceProvider, which needs the local
    VoiceBox server) and falls back to `secondary` (e.g. EstimatingVoiceProvider)
    on any error.
    Required for unattended autonomous operation: a transient network/service
    failure in the primary must never crash the whole content.run --
    SceneDurationMeasurer.measure() does not itself catch synthesis errors,
    so whatever provider it holds must never raise."""

    def __init__(self, primary: VoiceSynthesisProvider, secondary: VoiceSynthesisProvider):
        self.primary = primary
        self.secondary = secondary

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        try:
            return self.primary.synthesize(request)
        except Exception:
            return self.secondary.synthesize(request)


@dataclass(frozen=True)
class MeasuredDuration:
    total_seconds: float
    per_scene_ms: tuple[int, ...]
    word_boundaries: tuple[WordBoundary, ...] = field(default_factory=tuple)
    degraded: bool = False
    # Per-scene audio file paths, same order as per_scene_ms (empty string for
    # a scene whose provider didn't write a file, e.g. the estimating
    # fallback). The video pipeline concatenates these into one narration
    # track rather than re-synthesizing -- reusing the exact audio this
    # duration was measured from keeps word_boundaries/SFX timing accurate.
    audio_refs: tuple[str, ...] = field(default_factory=tuple)


class SceneDurationMeasurer:
    """Measures real narration duration scene-by-scene via a voice provider.

    Implements the ``DurationMeasurer`` shape the StoryEngine expects: given the
    scenes, return the summed measured duration (in seconds) plus per-scene
    milliseconds and word timings (usable later for subtitles).

    When a rate_learner is supplied, every non-degraded (genuinely
    synthesized, not estimated) measurement feeds back into it -- see
    ``record`` in ``measure`` below -- so StoryEngine's word-count targeting
    (``words_per_second``) keeps converging on the real rate instead of the
    original fixed guess.
    """

    def __init__(
        self,
        provider: VoiceSynthesisProvider,
        *,
        voice_id: str,
        rate: float = 0.0,
        pitch: float = 0.0,
        rate_learner: "object | None" = None,
    ):
        self.provider = provider
        self.voice_id = voice_id
        self.rate = rate
        self.pitch = pitch
        self.rate_learner = rate_learner

    def words_per_second(self) -> float:
        """Current best-known real speech rate for this voice: the learned
        running average once real samples exist, else the cold-start prior."""
        if self.rate_learner is None:
            return DEFAULT_WORDS_PER_SECOND
        return self.rate_learner.estimate(self.voice_id).words_per_second

    def measure(self, scenes) -> MeasuredDuration:
        per_scene: list[int] = []
        audio_refs: list[str] = []
        boundaries: list[WordBoundary] = []
        degraded = False
        offset = 0
        total_words = 0
        for scene in scenes:
            text = getattr(scene, "narration", "") or ""
            total_words += len(text.split())
            result = self.provider.synthesize(
                VoiceSynthesisRequest(text=text, voice_id=self.voice_id, rate=self.rate, pitch=self.pitch)
            )
            per_scene.append(result.duration_ms)
            audio_refs.append(result.audio_ref or "")
            degraded = degraded or result.degraded
            for boundary in result.word_boundaries:
                boundaries.append(
                    WordBoundary(boundary.word, offset + boundary.offset_ms, boundary.duration_ms)
                )
            offset += result.duration_ms
        total_ms = sum(per_scene)
        if self.rate_learner is not None and not degraded:
            self.rate_learner.record(self.voice_id, total_words, total_ms / 1000.0)
        return MeasuredDuration(
            total_seconds=total_ms / 1000.0,
            audio_refs=tuple(audio_refs),
            per_scene_ms=tuple(per_scene),
            word_boundaries=tuple(boundaries),
            degraded=degraded,
        )
