"""Kronara Pulse: el agente especializado en métricas y tendencias.

Es LÓGICA DE AGENTE sobre DATOS (no ingesta nada por sí solo): a partir de las
métricas de episodios ya publicados y de muestras de contenido similar/en
tendencia, produce recomendaciones editoriales accionables -- qué títulos y
ganchos funcionan, qué temas doblar, qué evitar.

Los DATOS reales (métricas por plataforma, muestras de tendencia) llegan de la
conexión de red (API nativa o agregador) o de un cosechador de tendencias; este
módulo solo razona sobre ellos. Router inyectado -> testeable con fakes.
"""

from __future__ import annotations

from typing import Any

from kronara.model_registry_v2 import ModelRequirements

_PERFORMANCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "what_works": {"type": "array", "items": {"type": "string"}},
        "what_to_change": {"type": "array", "items": {"type": "string"}},
        "title_formulas": {"type": "array", "items": {"type": "string"}},
        "next_topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["what_works", "what_to_change", "title_formulas", "next_topics"],
}

_TREND_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "patterns": {"type": "array", "items": {"type": "string"}},
        "title_formulas": {"type": "array", "items": {"type": "string"}},
        "angles_to_try": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["patterns", "title_formulas", "angles_to_try", "avoid"],
}


def analyze_performance(
    router: Any, *, episodes: "list[dict[str, Any]]", program: str = "", language: str = "es"
) -> dict[str, Any]:
    """Recomendaciones editoriales a partir de las métricas propias. ``episodes``
    = lista de {title, views, retention, engagement, hook, ...}. Best-effort."""
    if not episodes:
        return {"status": "no_data", "detail": "Sin métricas de episodios todavía (requiere la conexión de red)."}
    try:
        payload = router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(frozenset({"creative"}), structured_output=True),
            task="pulse.performance",
            system=(
                "Eres Kronara Pulse, analista de rendimiento editorial. A partir de las MÉTRICAS "
                "propias identificas qué funciona y qué cambiar, con recomendaciones ACCIONABLES y "
                "honestas (no inventes causas que los datos no respaldan). Cuando los episodios "
                "traigan señales de formato (content_kind, style_id, video_source_kind_counts = mix "
                "de fuentes de animación), correlaciónalas con el resultado: qué tipo de contenido, "
                "estilo visual o mezcla de metraje rinde mejor. Idioma indicado."
            ),
            input_payload={"language": language, "program": program, "episodes": episodes[:40]},
            response_schema=_PERFORMANCE_SCHEMA,
            max_tokens=768,
        )
        return {
            "status": "ok",
            "what_works": [str(x) for x in payload.get("what_works", ())],
            "what_to_change": [str(x) for x in payload.get("what_to_change", ())],
            "title_formulas": [str(x) for x in payload.get("title_formulas", ())],
            "next_topics": [str(x) for x in payload.get("next_topics", ())],
        }
    except Exception:
        return {"status": "error", "detail": "El análisis de rendimiento no se completó."}


def trend_brief(
    router: Any, *, samples: "list[dict[str, Any]]", niche: str = "", language: str = "es"
) -> dict[str, Any]:
    """Extrae qué funciona de muestras de contenido similar/en tendencia.
    ``samples`` = lista de {title, platform, views/likes, hook?}. Best-effort."""
    if not samples:
        return {"status": "no_data", "detail": "Sin muestras de tendencia (requiere un cosechador o la conexión)."}
    try:
        payload = router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(frozenset({"creative"}), structured_output=True),
            task="pulse.trends",
            system=(
                "Eres Kronara Pulse. A partir de MUESTRAS de contenido similar o en tendencia extraes "
                "patrones y fórmulas de título que funcionan en el nicho, ángulos para probar y qué "
                "evitar. No copies frases ni afirmes datos que las muestras no respaldan."
            ),
            input_payload={"language": language, "niche": niche, "samples": samples[:40]},
            response_schema=_TREND_SCHEMA,
            max_tokens=768,
        )
        return {
            "status": "ok",
            "patterns": [str(x) for x in payload.get("patterns", ())],
            "title_formulas": [str(x) for x in payload.get("title_formulas", ())],
            "angles_to_try": [str(x) for x in payload.get("angles_to_try", ())],
            "avoid": [str(x) for x in payload.get("avoid", ())],
        }
    except Exception:
        return {"status": "error", "detail": "El análisis de tendencias no se completó."}
