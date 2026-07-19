import json
from pathlib import Path

from kronara.embedding_registry import EmbeddingModelDescriptor
from kronara.model_registry_v2 import ModelCapabilityRegistryV2
from kronara.rag_v2 import DeterministicHashEmbedder, IngestDocument
from kronara.rag_v3 import RAGV3Index
from kronara.store import KronaraStore
from kronara.content_pipeline import ProductionContentPipeline


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
