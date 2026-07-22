"""Produce one complete episode using the REAL visual/audio stack end to end:
real edge-tts narration (network), real local SDXL images (GPU/CPU
inference), real ffmpeg composition and render. The story text itself is a
deterministic fixture (same pattern as create_fresh_visual_story.py) so this
proves the audio/image/composition/render chain specifically, without
spending model API credit on story generation -- that path was already
verified separately with real OpenRouter/Groq calls earlier this session.

Not part of content.run or the shipped app -- a manual verification script,
matching the project's existing scripts/create_fresh_visual_story.py pattern.
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
from kronara.image_gen import DiffusersImageProvider
from kronara.model_registry_v2 import ModelCapabilityRegistryV2
from kronara.rag_v2 import DeterministicHashEmbedder, IngestDocument
from kronara.rag_v3 import RAGV3Index
from kronara.render import FfmpegRenderer, find_ffmpeg
from kronara.speech_rate import SpeechRateLearner
from kronara.store import KronaraStore
from kronara.visual_style import VisualStyleRegistry, default_registry_path as visual_style_path
from kronara.voice import EdgeTtsVoiceProvider, EstimatingVoiceProvider, FallbackVoiceProvider
from test_production_content_vertical import FakeProductionAuthority, descriptor  # noqa: E402


STORY_ID = "real_stack_verification_20260722"
VOICE_ID = "es-BO-SofiaNeural"


class RealStackStoryAuthority(FakeProductionAuthority):
    """Deterministic narrative content -- story-generation model routing was
    already verified separately with real OpenRouter/Groq calls; this run's
    purpose is the audio/image/render chain, not re-proving that."""

    def invoke(self, tool_id, arguments):
        response = super().invoke(tool_id, arguments)
        task = arguments.get("task")
        if task == "editorial.brief":
            response["payload"] = {
                "title": "La luz que quedó encendida en la casa vacía",
                "premise": (
                    "Un electricista es llamado a una casa que lleva dos años "
                    "deshabitada porque una luz del segundo piso sigue "
                    "encendiéndose cada noche a la misma hora."
                ),
                "theme": "lo que se niega a apagarse",
            }
        elif task == "story.concepts":
            response["payload"]["concepts"] = [
                {
                    "concept_id": f"real_stack_concept_{index}",
                    "logline": (
                        "Un electricista revisa una instalación imposible y "
                        "descubre que la casa vacía nunca estuvo realmente sola."
                    ),
                    "promise": "Cada cable que corta explica menos de lo que oculta.",
                    "hook": "La luz llevaba dos años encendiéndose sin nadie adentro.",
                    "projected_retention": 0.84,
                }
                for index in range(1, 4)
            ]
        elif task == "story.scenes":
            narrations = (
                "Ruben entra a la casa con la llave que le dio la inmobiliaria y recorre la sala vacia iluminando cada rincon con su linterna de trabajo. En el tablero electrico del pasillo encuentra el interruptor del segundo piso quemado por dentro, con las marcas de un arco electrico que solo se producen cuando algo fuerza el mecanismo una y otra vez, noche tras noche, durante los dos años completos que la casa lleva deshabitada segun el papeleo que trae bajo el brazo.",
                "Sube por la escalera de madera contando los escalones que crujen bajo su peso y llega a una habitacion completamente vacia, sin muebles, sin cortinas, sin una sola caja olvidada por la mudanza. Lo unico que encuentra es una lampara de pie en la esquina, conectada a un cable largo que recorre el zocalo entero de la pared y termina en el suelo, sin llegar jamas a ninguna toma de corriente visible en los cuatro costados del cuarto.",
                "Se agacha junto a la lampara y la toca con el dorso de la mano, tal como le enseñaron a revisar instalaciones sospechosas antes de tocarlas con los dedos, y siente que la base todavia esta tibia, como si alguien la hubiera apagado apenas unos segundos antes de que el subiera la escalera, aunque el expediente que trajo impreso confirma que esta vivienda esta desconectada de la red electrica desde hace veinticuatro meses exactos.",
                "Baja de nuevo hasta la entrada y sale al jardin delantero para revisar el medidor exterior, el unico punto de la instalacion que en teoria deberia estar completamente muerto. La aguja de cobre se mueve despacio pero de forma constante, marcando un consumo activo en este preciso instante, mientras observa que el resto de las casas del vecindario, todas habitadas, permanecen completamente a oscuras a esta hora de la noche.",
                "Vuelve a subir siguiendo un zumbido electrico bajo y continuo que parece salir directamente de las paredes del pasillo, y al asomarse a la habitacion encuentra la lampara encendida otra vez, proyectando contra el techo la sombra nitida de alguien sentado en una silla que ya no esta ahi. La sombra se mueve un instante antes de desaparecer por completo, justo en el segundo exacto en que el enciende el haz de su propia linterna para iluminar la escena.",
                "Ruben decide terminar la revision de la unica forma que conoce y corta el cable con sus propias manos, guardando el extremo cortado como evidencia dentro de una bolsa plastica. Ya en la calle, con la puerta cerrada tras de si y el auto encendido, mira hacia la ventana del segundo piso por costumbre profesional y ve la misma luz encenderse otra vez detras del vidrio; firma el reporte esa misma noche, pero deja en blanco la casilla donde debia escribir, con sus propias palabras, lo que realmente acaba de ver.",
            )
            response["payload"]["scenes"] = [
                {
                    "scene_id": f"real_stack_scene_{index}",
                    "purpose": f"real_stack_event_{index}",
                    "narration": narrations[index - 1],
                    "target_seconds": 24,
                    "characters": ["Ruben"],
                    "seed_ids": [f"seed_{index}"] if index <= 3 else [],
                    "payoff_ids": [f"seed_{index - 3}"] if index > 3 else [],
                }
                for index in range(1, 7)
            ]
        return response


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
            document_id="real-stack-owned-dna",
            title="ADN narrativo propio",
            content=(
                "Historias originales con protagonistas activos, evidencia "
                "tecnica creible y un final que nunca confirma del todo lo "
                "sobrenatural."
            ),
            rights_mode="owned_original",
            language="es",
            scope="narrative",
            valid_from=0,
            valid_until=None,
        )
    )

    rate_learner = SpeechRateLearner(output_root / "speech_rate.db").initialize()
    voice_provider = FallbackVoiceProvider(
        EdgeTtsVoiceProvider(audio_dir=str(output_root / "voice")),
        EstimatingVoiceProvider(audio_dir=str(output_root / "voice"), rate_learner=rate_learner),
    )
    image_provider = DiffusersImageProvider(output_dir=str(output_root / "images"))
    visual_style_registry = VisualStyleRegistry.load(visual_style_path())

    pipeline = ProductionContentPipeline(
        authority=RealStackStoryAuthority(),
        store=store,
        rag=rag,
        model_registry=ModelCapabilityRegistryV2.load(
            ROOT / "config" / "models" / "registry.v2.json"
        ),
        artifact_root=output_root / "artifacts",
        voice_provider=voice_provider,
        voice_id=VOICE_ID,
        rate_learner=rate_learner,
        image_provider=image_provider,
        visual_style_registry=visual_style_registry,
        renderer=FfmpegRenderer(ffmpeg=ffmpeg),
    )
    result = pipeline.run(
        {
            "story_id": STORY_ID,
            "program_id": "viernes-paranormal",
            "subreddits": ["Historias"],
            "sort": "hot",
            "limit": 25,
            # The 6 scenes above measure ~143s of real edge-tts narration
            # (474 words at the es-BO-SofiaNeural measured rate of ~3.31
            # words/sec) -- target picked so that lands mid-window against
            # DurationQCReport's +-10% tolerance (story_engine.py:_duration_qc),
            # not to match any real program's actual target duration.
            "target_duration_seconds": 140,
        }
    )
    if result.get("status") != "completed":
        print(
            json.dumps(
                {
                    "status": result.get("status"),
                    "error_code": result.get("error_code"),
                    "selected_signal": result.get("selected_signal"),
                    "rejected_signals": result.get("rejected_signals"),
                    "story_id": STORY_ID,
                    "output_root": str(output_root),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        rag.close()
        store.close()
        raise SystemExit(1)

    saved = store.load_owned_story_artifact(STORY_ID)
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "error_code": result.get("error_code"),
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
                        "video_qc_issues",
                        "video_scene_count",
                        "video_shot_count",
                        "video_source_kind_counts",
                        "video_integrated_lufs",
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
