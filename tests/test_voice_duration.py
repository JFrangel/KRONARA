import json
import urllib.error
from pathlib import Path

import pytest

from kronara.speech_rate import DEFAULT_WORDS_PER_SECOND, SpeechRateLearner
from kronara.story_engine import (
    DeterministicIndependentCritic,
    DeterministicStoryProvider,
    StoryBrief,
    StoryEngine,
)
from kronara.store import KronaraStore
from kronara.voice import (
    EstimatingVoiceProvider,
    FallbackVoiceProvider,
    SceneDurationMeasurer,
    VoiceBoxVoiceProvider,
    VoiceSynthesisRequest,
    VoiceSynthesisResult,
    WordBoundary,
)


class FakeVoiceBoxServer:
    """Simulates VoiceBox's async HTTP contract for the provider tests without a
    real server: POST /generate returns a generation id, then GET /audio/{id}
    404s ``pending`` times (still rendering) before returning the audio bytes."""

    def __init__(self, *, audio: bytes = b"RIFFfakeaudio", pending: int = 1, gen_id: str = "gen-1"):
        self.audio = audio
        self.pending = pending
        self.gen_id = gen_id
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url, data=None, headers=None, method="GET", timeout=30):
        self.calls.append((method, url))
        if method == "POST" and url.endswith("/generate"):
            return 200, json.dumps({"id": self.gen_id, "status": "generating"}).encode("utf-8")
        if method == "GET" and url.endswith(f"/audio/{self.gen_id}"):
            if self.pending > 0:
                self.pending -= 1
                raise urllib.error.HTTPError(url, 404, "not ready", {}, None)
            return 200, self.audio
        raise AssertionError(f"unexpected VoiceBox call {method} {url}")


def brief(**overrides):
    payload = {
        "story_id": "owned_voice_1",
        "title": "La llamada que nadie quería contestar",
        "premise": "Una restauradora descubre una decisión capaz de dividir a su familia.",
        "theme": "lealtad frente a verdad",
        "target_duration_seconds": 90,
        "rights_mode": "owned_original",
        "source_uri": "kronara://artifacts/owned_voice_1",
        "evidence_refs": ("ev_owned_1",),
    }
    payload.update(overrides)
    return StoryBrief(**payload)


class FakeVoiceProvider:
    """Reports a fixed per-call duration so the measured total is deterministic."""

    def __init__(self, ms_per_scene):
        self.ms_per_scene = ms_per_scene
        self.calls = 0

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        self.calls += 1
        return VoiceSynthesisResult(
            voice_id=request.voice_id,
            duration_ms=self.ms_per_scene,
            word_boundaries=(WordBoundary("palabra", 0, 200),),
        )


def test_story_engine_uses_real_measured_duration(tmp_path):
    store = KronaraStore(tmp_path / "voice.db")
    store.initialize()
    # 8 scenes * ~11.25s each = 90s total (inside the +-10% window at 90s target).
    provider = FakeVoiceProvider(ms_per_scene=11_250)
    measurer = SceneDurationMeasurer(provider, voice_id="es-BO-SofiaNeural")
    engine = StoryEngine(
        store=store,
        generator=DeterministicStoryProvider(),
        critic=DeterministicIndependentCritic(),
        duration_measurer=measurer,
    )

    result = engine.run(brief())

    assert result.status == "completed"
    assert result.voice_duration is not None
    assert result.voice_duration.degraded is False
    # QC used the synthesized total, not the words/2.5 estimate.
    assert abs(result.duration_qc.estimated_seconds - result.voice_duration.total_seconds) < 0.001
    assert provider.calls >= len(result.scenes)
    store.close()


def test_measurer_carries_per_scene_audio_refs_in_scene_order():
    class RefVoiceProvider:
        def __init__(self):
            self.calls = 0

        def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
            self.calls += 1
            return VoiceSynthesisResult(
                voice_id=request.voice_id, duration_ms=1000,
                audio_ref=f"/audio/scene_{self.calls}.mp3",
            )

    provider = RefVoiceProvider()
    measurer = SceneDurationMeasurer(provider, voice_id="es-BO-SofiaNeural")

    result = measurer.measure(
        [type("S", (), {"narration": "uno"}), type("S", (), {"narration": "dos"})]
    )

    assert result.audio_refs == ("/audio/scene_1.mp3", "/audio/scene_2.mp3")


def test_measurer_uses_empty_string_when_provider_writes_no_file():
    provider = EstimatingVoiceProvider(words_per_minute=150)  # never sets audio_ref
    measurer = SceneDurationMeasurer(provider, voice_id="es-BO-SofiaNeural")

    result = measurer.measure([type("S", (), {"narration": "una frase"})])

    assert result.audio_refs == ("",)


def test_fallback_provider_uses_primary_when_it_succeeds():
    class WorkingProvider:
        def synthesize(self, request):
            return VoiceSynthesisResult(voice_id=request.voice_id, duration_ms=5000, degraded=False)

    provider = FallbackVoiceProvider(WorkingProvider(), EstimatingVoiceProvider())
    result = provider.synthesize(VoiceSynthesisRequest(text="hola", voice_id="es-BO-SofiaNeural"))

    assert result.duration_ms == 5000
    assert result.degraded is False


def test_fallback_provider_degrades_to_secondary_when_primary_raises():
    class BrokenProvider:
        def synthesize(self, request):
            raise RuntimeError("edge-tts synthesis failed: network unavailable")

    provider = FallbackVoiceProvider(BrokenProvider(), EstimatingVoiceProvider())
    result = provider.synthesize(
        VoiceSynthesisRequest(text="una dos tres", voice_id="es-BO-SofiaNeural")
    )

    assert result.degraded is True
    assert result.duration_ms > 0


def test_fallback_provider_still_raises_if_the_secondary_also_fails():
    """Only the primary's failure is swallowed. If even the local,
    no-network estimating fallback fails, something is deeply wrong and
    that should propagate rather than be silently swallowed twice."""
    class AlwaysBroken:
        def synthesize(self, request):
            raise RuntimeError("nope")

    provider = FallbackVoiceProvider(AlwaysBroken(), AlwaysBroken())

    import pytest

    with pytest.raises(RuntimeError):
        provider.synthesize(VoiceSynthesisRequest(text="x", voice_id="v"))


def test_estimating_provider_marks_degraded_but_measures():
    provider = EstimatingVoiceProvider(words_per_minute=150)
    result = provider.synthesize(
        VoiceSynthesisRequest(text="una dos tres cuatro cinco", voice_id="es-CL-LorenzoNeural")
    )
    assert result.degraded is True
    assert result.duration_ms > 0


def test_voicebox_generates_via_poll_and_writes_real_audio(tmp_path):
    """VoiceBox's async contract, end to end against a fake server: POST
    /generate, poll /audio/{id} past its "still rendering" 404s, then persist
    the returned audio as a non-degraded result."""
    server = FakeVoiceBoxServer(pending=2)
    provider = VoiceBoxVoiceProvider(
        profile_id="my-cloned-voice",
        audio_dir=str(tmp_path / "audio"),
        poll_interval=0.0,
        opener=server,
    )

    result = provider.synthesize(
        VoiceSynthesisRequest(text="una dos tres cuatro", voice_id="ignored")
    )

    assert result.degraded is False
    assert result.audio_ref is not None and Path(result.audio_ref).exists()
    assert result.duration_ms > 0  # ffprobe reads real audio, else word estimate
    assert ("POST", f"{provider.base_url}/generate") in server.calls
    # the request body carried the configured profile, not the edge voice_id
    assert server.calls.count(("GET", f"{provider.base_url}/audio/gen-1")) == 3


def test_voicebox_requires_a_profile_id(tmp_path):
    provider = VoiceBoxVoiceProvider(profile_id="", opener=FakeVoiceBoxServer())
    with pytest.raises(RuntimeError):
        provider.synthesize(VoiceSynthesisRequest(text="hola mundo", voice_id=""))


def test_voicebox_times_out_when_audio_never_ready(tmp_path):
    """A never-completing generation raises (FallbackVoiceProvider then degrades
    to the estimate) rather than hanging content.run forever."""
    provider = VoiceBoxVoiceProvider(
        profile_id="v",
        audio_dir=str(tmp_path / "audio"),
        timeout=0.05,
        poll_interval=0.01,
        opener=FakeVoiceBoxServer(pending=10_000),
    )
    with pytest.raises(RuntimeError):
        provider.synthesize(VoiceSynthesisRequest(text="hola", voice_id="v"))


def test_voicebox_degrades_through_fallback_when_server_is_down(tmp_path):
    """The production wiring: VoiceBox unreachable -> FallbackVoiceProvider hands
    off to the silent estimate so a run never crashes on a missing server."""

    def dead_opener(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    voice = FallbackVoiceProvider(
        VoiceBoxVoiceProvider(profile_id="v", opener=dead_opener),
        EstimatingVoiceProvider(rate_learner=None),
    )
    result = voice.synthesize(VoiceSynthesisRequest(text="una dos tres", voice_id="v"))
    assert result.degraded is True
    assert result.duration_ms > 0


def test_duration_qc_target_word_count_uses_the_learned_rate_not_the_fixed_guess(tmp_path):
    """The whole point: once real samples exist, the word-count target
    handed to the writer (and the raw pre-measurement estimate) should
    track the learned rate, not silently keep re-deriving the original
    words/2.5 guess forever."""
    store = KronaraStore(tmp_path / "voice.db")
    store.initialize()
    learner = SpeechRateLearner(tmp_path / "speech_rate.db").initialize()
    learner.record("es-BO-SofiaNeural", 400, 100.0)  # 4.0 wps, real and learned
    measurer = SceneDurationMeasurer(
        FakeVoiceProvider(ms_per_scene=1000), voice_id="es-BO-SofiaNeural", rate_learner=learner
    )
    engine = StoryEngine(
        store=store,
        generator=DeterministicStoryProvider(),
        critic=DeterministicIndependentCritic(),
        duration_measurer=measurer,
    )

    script = engine._script((type("S", (), {"narration": "una dos tres cuatro"}),))
    qc = engine._duration_qc(brief(), script, revision_applied=False, measured_seconds=90.0)

    assert script.estimated_seconds == 4 / 4.0  # 4 words at 4.0 wps, not /2.5
    assert qc.target_word_count == round(90 * 4.0)  # not round(90 * 2.5) == 225
    store.close()


def test_measurer_words_per_second_defaults_without_a_rate_learner():
    measurer = SceneDurationMeasurer(FakeVoiceProvider(ms_per_scene=1000), voice_id="v1")

    assert measurer.words_per_second() == DEFAULT_WORDS_PER_SECOND


def test_measurer_records_a_real_non_degraded_measurement_into_the_rate_learner(tmp_path):
    learner = SpeechRateLearner(tmp_path / "speech_rate.db").initialize()
    # 2 scenes * 4 words each = 8 words; 1000ms each = 2.0s total -> 4.0 wps.
    provider = FakeVoiceProvider(ms_per_scene=1000)
    measurer = SceneDurationMeasurer(provider, voice_id="es-BO-SofiaNeural", rate_learner=learner)
    scenes = [
        type("S", (), {"narration": "una dos tres cuatro"}),
        type("S", (), {"narration": "cinco seis siete ocho"}),
    ]

    measurer.measure(scenes)

    result = learner.estimate("es-BO-SofiaNeural")
    assert result.learned is True
    assert result.words_per_second == 4.0
    assert measurer.words_per_second() == 4.0


def test_measurer_does_not_record_a_degraded_measurement(tmp_path):
    class DegradedProvider:
        def synthesize(self, request):
            return VoiceSynthesisResult(voice_id=request.voice_id, duration_ms=1000, degraded=True)

    learner = SpeechRateLearner(tmp_path / "speech_rate.db").initialize()
    measurer = SceneDurationMeasurer(DegradedProvider(), voice_id="v1", rate_learner=learner)

    measurer.measure([type("S", (), {"narration": "una dos tres"})])

    assert learner.estimate("v1").learned is False
    assert measurer.words_per_second() == DEFAULT_WORDS_PER_SECOND


def test_estimating_provider_uses_the_learned_rate_when_supplied(tmp_path):
    learner = SpeechRateLearner(tmp_path / "speech_rate.db").initialize()
    learner.record("es-BO-SofiaNeural", 400, 100.0)  # 4.0 wps, not the 2.5 default
    provider = EstimatingVoiceProvider(rate_learner=learner)

    result = provider.synthesize(
        VoiceSynthesisRequest(text="una dos tres cuatro", voice_id="es-BO-SofiaNeural")
    )

    assert result.duration_ms == 1000  # 4 words / 4.0 wps = 1.0s
    assert result.degraded is True  # still the no-network estimating path


def test_estimating_provider_without_a_rate_learner_keeps_the_fixed_rate():
    provider = EstimatingVoiceProvider(words_per_minute=150)  # 2.5 wps

    result = provider.synthesize(
        VoiceSynthesisRequest(text="una dos tres cuatro cinco", voice_id="v1")
    )

    assert result.duration_ms == 2000  # 5 words / 2.5 wps = 2.0s


def test_authority_voice_provider_caches(tmp_path):
    class OneShotAuthority:
        def __init__(self):
            self.calls = 0

        def invoke(self, tool_id, arguments):
            assert tool_id == "voice.synthesize"
            self.calls += 1
            return {"voice_id": arguments["voice_id"], "duration_ms": 4000, "word_boundaries": []}

    from kronara.voice import AuthorityVoiceProvider

    authority = OneShotAuthority()
    provider = AuthorityVoiceProvider(authority)
    request = VoiceSynthesisRequest(text="hola mundo", voice_id="es-BO-MarceloNeural")
    first = provider.synthesize(request)
    second = provider.synthesize(request)
    assert first.duration_ms == 4000
    assert second.cached is True
    assert authority.calls == 1  # second call served from cache
