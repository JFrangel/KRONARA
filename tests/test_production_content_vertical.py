import json
import subprocess
from pathlib import Path

import pytest

from kronara.authority_client import AuthorityInvocationError
from kronara.embedding_registry import EmbeddingModelDescriptor
from kronara.image_gen import PlaceholderImageProvider
from kronara.model_registry_v2 import ModelCapabilityRegistryV2
from kronara.rag_v2 import DeterministicHashEmbedder, IngestDocument
from kronara.rag_v3 import RAGV3Index
from kronara.render import FfmpegRenderer, find_ffmpeg
from kronara.store import KronaraStore
from kronara.content_pipeline import ProductionContentPipeline
from kronara.voice import VoiceSynthesisRequest, VoiceSynthesisResult, WordBoundary


ROOT = Path(__file__).resolve().parents[1]


def descriptor():
    return EmbeddingModelDescriptor(
        alias="deterministic_dev",
        provider="kronara",
        model_id="kronara/deterministic-hash",
        kind="embedding",
        dimensions=64,
        max_tokens=2048,
        languages=("es",),
        normalized=False,
        query_instruction="",
        license="internal-test-only",
        version_hash="deterministic-hash-v1",
        privacy="local",
        health="development_only",
    )


class FakeProductionAuthority:
    def __init__(self):
        self.calls = []

    def invoke(self, tool_id, arguments):
        self.calls.append((tool_id, arguments))
        if tool_id == "reddit.list_signals":
            return {
                "schema_version": 1,
                "signals": [
                    {
                        "source_id": "trend-safe-1",
                        "source_uri": "https://reddit.com/r/Historias/trend-safe-1",
                        "title": "Un audio familiar termina antes de revelar una decisión",
                        "selftext": "ESTE CUERPO EXTERNO NO DEBE CRUZAR NI PERSISTIR",
                        "score": 680,
                        "comments": 94,
                        "created_at": 1_799_978_400,
                        "observed_length": 2100,
                        "language": None,
                        "self_post": True,
                        "nsfw": False,
                        "author_deleted": False,
                        "post_deleted": False,
                        "crosspost": False,
                    },
                    {
                        "source_id": "trend-nsfw",
                        "source_uri": "https://reddit.com/r/Historias/trend-nsfw",
                        "title": "Contenido explícito",
                        "score": 900,
                        "comments": 120,
                        "created_at": 1_799_982_000,
                        "observed_length": 3000,
                        "language": "es",
                        "self_post": True,
                        "nsfw": True,
                        "author_deleted": False,
                        "post_deleted": False,
                        "crosspost": False,
                    },
                ],
                "after": None,
                "receipt": {
                    "receipt_id": "rr-safe-1",
                    "query_hash": "hash-safe-1",
                    "contract_reference": "contract-approved",
                    "observed_at": 1_800_000_000,
                    "count": 2,
                },
            }
        if tool_id == "model.health":
            return {
                "models": {
                    "qwen/qwen3-235b-a22b": "healthy",
                    "moonshotai/kimi-k2": "healthy",
                    "nvidia/nemotron-3-super-120b-a12b:free": "healthy",
                    "tencent/hy3:free": "healthy",
                }
            }
        task = arguments["task"]
        if task == "editorial.brief":
            payload = {
                "title": "El silencio que sabía su nombre",
                "premise": "Una restauradora descubre una decisión propia capaz de romper una promesa familiar.",
                "theme": "lealtad frente a verdad",
            }
        elif task == "story.inspiration":
            payload = {"angles": ["evidencia incompleta", "decisión irreversible"]}
        elif task == "story.concepts":
            payload = {
                "concepts": [
                    {
                        "concept_id": f"concept_{index}",
                        "logline": f"Mara enfrenta el costo original del concepto {index}.",
                        "promise": "Cada pista obliga a elegir.",
                        "hook": f"Una respiración cambia la prueba {index}.",
                        "projected_retention": 0.80 + index / 100,
                    }
                    for index in range(1, 4)
                ]
            }
        elif task == "story.blueprint":
            payload = {
                "beats": [
                    {
                        "beat_id": f"beat_{index}",
                        "cause": f"causa verificable {index}",
                        "effect": f"decisión irreversible {index}",
                        "event": f"evento_original_{index}",
                        "seed_id": f"seed_{index}" if index <= 3 else None,
                        "payoff_for": f"seed_{index - 3}" if index > 3 else None,
                    }
                    for index in range(1, 7)
                ]
            }
        elif task == "story.scenes":
            narration = (
                "Mara escucha una anomalía concreta y conserva la copia verificable. "
                "Compara la hora, descarta una explicación cómoda y toma una decisión "
                "que aumenta el costo familiar. La pista abre una pregunta nueva mientras "
                "la consecuencia anterior impide retroceder sin perder la evidencia."
            )
            payload = {
                "scenes": [
                    {
                        "scene_id": f"scene_{index}",
                        "purpose": f"evento_original_{index}",
                        "narration": narration,
                        "target_seconds": 15,
                        "characters": ["Mara"],
                        "seed_ids": [f"seed_{index}"] if index <= 3 else [],
                        "payoff_ids": [f"seed_{index - 3}"] if index > 3 else [],
                    }
                    for index in range(1, 7)
                ]
            }
        elif task == "story.revise":
            scenes = arguments["input"]["scenes"]
            target = arguments["input"]["revision"].get("target_word_count")
            if target:
                per_scene = target // len(scenes)
                for scene in scenes:
                    scene["narration"] = " ".join(scene["narration"].split()[:per_scene]) + "."
            payload = {"scenes": scenes}
        elif task == "story.critique":
            payload = {
                "passed": True,
                "scores": {
                    key: 8.5
                    for key in (
                        "hook", "clarity", "conflict", "escalation", "agency",
                        "coherence", "credibility", "originality", "retention",
                        "payoff", "production_fit",
                    )
                },
                "issues": [],
                "revision": {},
            }
        else:
            raise AssertionError(task)
        selected = arguments["candidates"][0]
        return {
            "payload": payload,
            "provider": selected["provider"],
            "model": selected["model_id"],
            "fallback_used": False,
            "usage": {"total_tokens": 100},
        }


def test_reddit_to_owned_story_vertical_is_cited_recoverable_and_body_free(tmp_path):
    authority = FakeProductionAuthority()
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    rag = RAGV3Index(tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64))
    rag.upsert(
        IngestDocument(
            document_id="owned-dna-1",
            title="ADN narrativo propio",
            content="Las historias propias usan protagonistas activas, evidencia y decisiones irreversibles.",
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )
    pipeline = ProductionContentPipeline(
        authority=authority,
        store=store,
        rag=rag,
        model_registry=ModelCapabilityRegistryV2.load(
            ROOT / "config" / "models" / "registry.v2.json"
        ),
        artifact_root=tmp_path / "artifacts",
    )

    result = pipeline.run(
        {
            "story_id": "owned-production-1",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
        }
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["status"] == "completed"
    assert result["selected_signal"]["source_id"] == "trend-safe-1"
    assert result["rejected_signals"] == {"nsfw": 1}
    assert result["reddit_receipt_id"] == "rr-safe-1"
    assert result["rag_citations"]
    assert result["story"]["generator_family"] == "qwen-routed"
    assert result["story"]["critic_family"] == "kimi-routed"
    assert 81 <= result["story"]["estimated_seconds"] <= 99
    assert result["story"]["duration_qc"]["passed"]
    assert "ESTE CUERPO EXTERNO" not in serialized
    assert "selftext" not in serialized
    artifact = store.load_owned_story_artifact("owned-production-1")
    assert Path(artifact["path"]).read_text(encoding="utf-8") == result["story"]["script"]
    replay = json.dumps([event.payload for event in store.replay("content:owned-production-1")])
    assert "ESTE CUERPO EXTERNO" not in replay
    completed_tools = {
        event.tool_id
        for event in store.list_tool_traces("content:owned-production-1")
        if event.status == "completed"
    }
    assert {"reddit.list_signals", "model.complete", "knowledge.retrieve"} <= completed_tools
    store.close()
    rag.close()


def test_content_run_program_id_flows_into_the_saved_artifact(tmp_path):
    """params["program_id"] must reach StoryBrief and the persisted artifact --
    both V3's per-program visual style lookup and the Programas UI's nested
    Episodios tab (episodes.list filtered by program_id) depend on this, and
    neither was ever exercised by a test before this."""
    authority = FakeProductionAuthority()
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    rag = RAGV3Index(tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64))
    rag.upsert(
        IngestDocument(
            document_id="owned-dna-1",
            title="ADN narrativo propio",
            content="Las historias propias usan protagonistas activas, evidencia y decisiones irreversibles.",
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )
    pipeline = ProductionContentPipeline(
        authority=authority,
        store=store,
        rag=rag,
        model_registry=ModelCapabilityRegistryV2.load(
            ROOT / "config" / "models" / "registry.v2.json"
        ),
        artifact_root=tmp_path / "artifacts",
    )

    result = pipeline.run(
        {
            "story_id": "owned-program-tagged-1",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
            "program_id": "viernes-paranormal",
        }
    )

    assert result["status"] == "completed"
    artifact = store.load_owned_story_artifact("owned-program-tagged-1")
    assert artifact["program_id"] == "viernes-paranormal"
    listed = store.list_owned_story_artifacts(limit=10)
    assert any(
        item["story_id"] == "owned-program-tagged-1" and item["program_id"] == "viernes-paranormal"
        for item in listed
    )
    store.close()
    rag.close()


class RedditDisabledAuthority(FakeProductionAuthority):
    """Simulates the real, common case: no KRONARA_REDDIT_* OAuth credentials
    configured (reddit.rs reports reddit_disabled_by_policy). This is what a
    freshly installed Kronara actually looks like -- the project's own design
    principle is that discovery never requires those credentials in the
    first place (see harvest_reddit.py, knowledge/reddit-sources/)."""

    def invoke(self, tool_id, arguments):
        if tool_id == "reddit.list_signals":
            self.calls.append((tool_id, arguments))
            raise AuthorityInvocationError("reddit_disabled_by_policy")
        return super().invoke(tool_id, arguments)


def test_reddit_oauth_unavailable_falls_back_to_public_rss_and_still_produces_a_story(tmp_path, monkeypatch):
    from kronara.reddit_rss import RedditRssReader, RssPost

    canned_posts = [
        RssPost(
            subreddit="Historias",
            title="Un audio familiar termina antes de revelar una decision",
            link="https://www.reddit.com/r/Historias/comments/abc123/un_audio/",
            published="2026-07-19T12:00:00+00:00",
        ),
    ]
    monkeypatch.setattr(RedditRssReader, "trending", lambda self, *a, **k: canned_posts)

    authority = RedditDisabledAuthority()
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    rag = RAGV3Index(tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64))
    rag.upsert(
        IngestDocument(
            document_id="owned-dna-1",
            title="ADN narrativo propio",
            content="Las historias propias usan protagonistas activas, evidencia y decisiones irreversibles.",
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )
    pipeline = ProductionContentPipeline(
        authority=authority,
        store=store,
        rag=rag,
        model_registry=ModelCapabilityRegistryV2.load(
            ROOT / "config" / "models" / "registry.v2.json"
        ),
        artifact_root=tmp_path / "artifacts",
    )

    result = pipeline.run(
        {
            "story_id": "owned-rss-fallback-1",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
        }
    )

    assert result["status"] == "completed"
    assert result["selected_signal"]["source_uri"] == canned_posts[0].link
    assert result["reddit_receipt_id"].startswith("rss_")
    fallback_events = [
        event.payload for event in store.replay("content:owned-rss-fallback-1")
        if event.kind == "content.reddit_fallback_rss"
    ]
    assert len(fallback_events) == 1
    assert fallback_events[0]["reason"] == "reddit_disabled_by_policy"
    store.close()
    rag.close()


def test_rss_fallback_signals_have_honest_zero_engagement_not_fabricated_numbers(tmp_path, monkeypatch):
    from kronara.reddit_rss import RedditRssReader, RssPost

    monkeypatch.setattr(
        RedditRssReader, "trending",
        lambda self, *a, **k: [RssPost("Historias", "Titulo de prueba real", "https://www.reddit.com/r/Historias/comments/xyz/", "2026-07-19T12:00:00+00:00")],
    )
    authority = RedditDisabledAuthority()
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    pipeline = ProductionContentPipeline(
        authority=authority, store=store,
        rag=RAGV3Index(tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64)),
        model_registry=ModelCapabilityRegistryV2.load(ROOT / "config" / "models" / "registry.v2.json"),
        artifact_root=tmp_path / "artifacts",
    )

    _receipt, _now, signals = pipeline._rss_fallback_signals(["Historias"], {"limit": 25})

    assert len(signals) == 1
    assert signals[0].score == 0
    assert signals[0].comments == 0
    assert signals[0].velocity == 0.0
    assert signals[0].theme_hint == "Titulo de prueba real"
    store.close()


FFMPEG_MISSING = find_ffmpeg("ffmpeg") is None


class FakeRealAudioVoiceProvider:
    """Writes a real short WAV per scene via ffmpeg (standing in for
    edge-tts) so the pipeline's real voice_duration.audio_refs are genuine,
    playable files -- exactly what produce_episode_video() requires."""

    def __init__(self, ffmpeg: str, audio_dir: Path):
        self.ffmpeg = ffmpeg
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._count = 0

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        self._count += 1
        path = self.audio_dir / f"scene_{self._count}.wav"
        duration_s = max(1.0, len(request.text.split()) / 2.5)
        subprocess.run(
            [self.ffmpeg, "-y", "-f", "lavfi", "-i",
             f"sine=frequency={200 + self._count * 10}:duration={duration_s:.2f}", str(path)],
            capture_output=True, check=True,
        )
        return VoiceSynthesisResult(
            voice_id=request.voice_id,
            duration_ms=int(duration_s * 1000),
            audio_ref=str(path),
            word_boundaries=(WordBoundary(request.text.split()[0] if request.text.split() else "x", 0, 300),),
        )


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_content_run_produces_a_real_video_when_visual_stage_is_configured(tmp_path):
    """V8's wiring proof: the same reddit-to-script vertical, but with
    image_provider/renderer configured, actually produces a real MP4 as
    part of one content.run() call -- not a separate manual step."""
    ffmpeg = find_ffmpeg("ffmpeg")
    authority = FakeProductionAuthority()
    store = KronaraStore(tmp_path / "runtime.db")
    store.initialize()
    rag = RAGV3Index(tmp_path / "knowledge.db", descriptor(), DeterministicHashEmbedder(64))
    rag.upsert(
        IngestDocument(
            document_id="owned-dna-1",
            title="ADN narrativo propio",
            content="Las historias propias usan protagonistas activas, evidencia y decisiones irreversibles.",
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )
    pipeline = ProductionContentPipeline(
        authority=authority,
        store=store,
        rag=rag,
        model_registry=ModelCapabilityRegistryV2.load(
            ROOT / "config" / "models" / "registry.v2.json"
        ),
        artifact_root=tmp_path / "artifacts",
        voice_provider=FakeRealAudioVoiceProvider(ffmpeg, tmp_path / "voice"),
        image_provider=PlaceholderImageProvider(output_dir=str(tmp_path / "images")),
        renderer=FfmpegRenderer(ffmpeg=ffmpeg),
    )

    result = pipeline.run(
        {
            "story_id": "owned-production-video-1",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
        }
    )

    assert result["status"] == "completed"
    assert result["video"] is not None
    assert result["video"]["status"] == "completed", result["video"]
    assert Path(result["video"]["output_path"]).exists()
    assert result["video"]["scene_count"] == 6
    assert sum(result["video"]["source_kind_counts"].values()) == 6
    events = {event.kind for event in store.replay("content:owned-production-video-1")}
    assert "content.completed" in events
    store.close()
    rag.close()


@pytest.mark.skipif(FFMPEG_MISSING, reason="ffmpeg not installed")
def test_operations_service_threads_the_visual_stack_through_to_content_run(tmp_path):
    """The gap this closes: OperationsService (what sidecar.py's serve()
    actually constructs for the real running app) previously had no way to
    receive image_provider/renderer/voice_provider at all, so content.run
    from the real app could only ever produce text -- even though
    ProductionContentPipeline itself has supported these params since V8.
    Proves the fix at the layer the real app actually uses, not just at
    ProductionContentPipeline directly."""
    from kronara.operations_service import OperationsService

    ffmpeg = find_ffmpeg("ffmpeg")
    authority = FakeProductionAuthority()
    service = OperationsService(
        tmp_path / "runtime",
        resource_root=ROOT,
        authority=authority,
        voice_provider=FakeRealAudioVoiceProvider(ffmpeg, tmp_path / "voice"),
        image_provider=PlaceholderImageProvider(output_dir=str(tmp_path / "images")),
        renderer=FfmpegRenderer(ffmpeg=ffmpeg),
    )
    service._rag.upsert(
        IngestDocument(
            document_id="owned-dna-2",
            title="ADN narrativo propio",
            content="Las historias propias usan protagonistas activas, evidencia y decisiones irreversibles.",
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )

    result = service.content_run(
        {
            "story_id": "owned-production-video-2",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
        }
    )

    assert result["status"] == "completed"
    assert result["video"] is not None
    assert result["video"]["status"] == "completed", result["video"]
    assert Path(result["video"]["output_path"]).exists()
    service.close()
