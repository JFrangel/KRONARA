"""Create one fresh, offline visual story for local UI/player validation.

This intentionally exercises the real ProductionContentPipeline, image
provider and FFmpeg renderer without calling paid models or publishing
anything. It is a development fixture generator, not an agent scheduler.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tests"))

from kronara.content_pipeline import ProductionContentPipeline
from kronara.image_gen import PlaceholderImageProvider
from kronara.model_registry_v2 import ModelCapabilityRegistryV2
from kronara.rag_v2 import DeterministicHashEmbedder, IngestDocument
from kronara.rag_v3 import RAGV3Index
from kronara.render import FfmpegRenderer, find_ffmpeg
from kronara.store import KronaraStore
from kronara.voice import VoiceSynthesisResult, WordBoundary
from test_production_content_vertical import (  # noqa: E402
    FakeProductionAuthority,
    FakeRealAudioVoiceProvider,
    descriptor,
)


STORY_ID = "fresh_viernes_20260721"


class FreshStoryAuthority(FakeProductionAuthority):
    """Deterministic authority with a new brief and new narrative material."""

    def invoke(self, tool_id, arguments):
        response = super().invoke(tool_id, arguments)
        task = arguments.get("task")
        if task == "editorial.brief":
            response["payload"] = {
                "title": "La llamada que llegó después del silencio",
                "premise": (
                    "Cuando Mara recibe una llamada desde un teléfono desconectado, "
                    "debe elegir entre borrar la grabación o escuchar la última "
                    "advertencia de su hermano."
                ),
                "theme": "duelo frente a verdad",
            }
        elif task == "story.concepts":
            response["payload"]["concepts"] = [
                {
                    "concept_id": f"fresh_concept_{index}",
                    "logline": (
                        "Mara sigue la pista de una llamada imposible y descubre que "
                        "cada minuto de silencio exige una decisión."
                    ),
                    "promise": "La evidencia cambia el sentido de la pérdida.",
                    "hook": "El teléfono sonó con la línea cortada.",
                    "projected_retention": 0.86,
                }
                for index in range(1, 4)
            ]
        elif task == "story.scenes":
            narrations = (
                "El teléfono de Mara suena junto a la ventana aunque lleva dos meses sin batería. Al contestar, una respiración pronuncia su nombre y se corta antes de que pueda preguntar quién llama. Ella mira el reloj, anota la hora y decide no contarle a nadie todavía.",
                "Mara guarda la grabación y revisa la casa habitación por habitación. Todo parece normal, pero la llamada dejó encendida una luz del pasillo que ella recuerda haber apagado. En el suelo encuentra una marca de polvo interrumpida frente a la puerta del fondo.",
                "La segunda llamada llega a la misma hora. Esta vez la voz le pide que no abra la puerta del fondo y menciona una cicatriz que solo conocía su hermano. Mara reconoce la respiración, pero se obliga a escucharla completa sin responder.",
                "Mara pide a la compañía el registro de la línea. La respuesta es imposible: el número fue desconectado el día del entierro, pero la llamada figura en su teléfono con fecha de hoy. La operadora le recomienda revisar la configuración; Mara sabe que no es un error.",
                "Un golpe suena detrás de la puerta. Mara activa la cámara, copia los archivos y encuentra en el audio un ruido de llaves que coincide con el cajón de su hermano. La imagen de seguridad muestra el pasillo vacío, aunque la sombra bajo la puerta se mueve.",
                "En vez de borrar la prueba, Mara publica la grabación para que alguien más pueda escucharla. Cuando termina, el teléfono vuelve a sonar desde el interior de la casa. Esta vez la pantalla muestra una llamada entrante con su propio nombre y la puerta comienza a abrirse.",
            )
            response["payload"]["scenes"] = [
                {
                    "scene_id": f"fresh_scene_{index}",
                    "purpose": f"fresh_event_{index}",
                    "narration": narrations[index - 1],
                    "target_seconds": 15,
                    "characters": ["Mara"],
                    "seed_ids": [f"seed_{index}"] if index <= 3 else [],
                    "payoff_ids": [f"seed_{index - 3}"] if index > 3 else [],
                }
                for index in range(1, 7)
            ]
        return response


class FreshAudioVoiceProvider(FakeRealAudioVoiceProvider):
    """Write playable audio and useful word timings for readable captions."""

    def synthesize(self, request):
        result = super().synthesize(request)
        words = request.text.split()
        if not words:
            return result
        slot_ms = max(120, result.duration_ms // len(words))
        boundaries = tuple(
            WordBoundary(word, index * slot_ms, max(100, slot_ms - 40))
            for index, word in enumerate(words)
        )
        return VoiceSynthesisResult(
            voice_id=result.voice_id,
            duration_ms=result.duration_ms,
            audio_ref=result.audio_ref,
            word_boundaries=boundaries,
        )


def main() -> None:
    ffmpeg = find_ffmpeg("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg no está disponible")

    output_root = ROOT / ".kronara" / "runtime" / STORY_ID
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    store = KronaraStore(output_root / "kronara.db")
    store.initialize()
    rag = RAGV3Index(
        output_root / "knowledge.db", descriptor(), DeterministicHashEmbedder(64)
    )
    rag.upsert(
        IngestDocument(
            document_id="fresh-owned-dna",
            title="ADN narrativo propio",
            content=(
                "Historias originales con protagonistas activas, evidencia "
                "preparada, decisiones irreversibles y consecuencias proporcionales."
            ),
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )

    pipeline = ProductionContentPipeline(
        authority=FreshStoryAuthority(),
        store=store,
        rag=rag,
        model_registry=ModelCapabilityRegistryV2.load(
            ROOT / "config" / "models" / "registry.v2.json"
        ),
        artifact_root=output_root / "artifacts",
        voice_provider=FreshAudioVoiceProvider(ffmpeg, output_root / "voice"),
        image_provider=PlaceholderImageProvider(output_dir=str(output_root / "images")),
        renderer=FfmpegRenderer(ffmpeg=ffmpeg),
    )
    result = pipeline.run(
        {
            "story_id": STORY_ID,
            "program_id": "viernes-paranormal",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
        }
    )
    saved = store.load_owned_story_artifact(STORY_ID)
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "story_id": STORY_ID,
                "title": saved["metadata"].get("title"),
                "program_id": saved.get("program_id"),
                "video": result.get("video"),
                "saved_metadata": {
                    key: saved["metadata"].get(key)
                    for key in (
                        "video_status",
                        "video_path",
                        "cover_image_path",
                        "video_qc_passed",
                        "video_scene_count",
                    )
                },
                "output_root": str(output_root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    rag.close()
    store.close()


if __name__ == "__main__":
    main()
