"""Agente de red social: packaging por plataforma + respuestas a comentarios.

Es LÓGICA DE AGENTE sobre el GUION (no toca la red): a partir de lo que dice el
guion genera título/descripción/hashtags adaptados a cada plataforma, y redacta
respuestas a comentarios ancladas en el contenido real del episodio.

La publicación y la LECTURA de comentarios reales las hace la conexión de red
(API nativa o agregador tipo Ayrshare/Postiz), NO este módulo. Aquí solo vive lo
que el agente "piensa/escribe"; el router se inyecta -> testeable con fakes.
"""

from __future__ import annotations

from typing import Any

from kronara.model_registry_v2 import ModelRequirements

# Cómo adapta el agente el packaging a cada plataforma (alcance, formato, tono).
PLATFORM_STYLE = {
    "facebook": "Facebook Reels: título-gancho claro + descripción cálida que invita a ver hasta el final; 2-4 hashtags amplios.",
    "instagram": "Instagram Reels: caption breve y con ritmo; gancho en la primera línea; 4-6 hashtags de nicho + alcance.",
    "youtube": "YouTube Shorts: título con intriga y palabras que la gente busca (SEO), sin clickbait falso; descripción de 1-2 líneas.",
    "tiktok": "TikTok: caption muy corto y directo; 3-5 hashtags del nicho y de tendencia; nada de relleno.",
    "aggregator": "Genérico multi-red: título y descripción neutros y fuertes, hashtags moderados que sirvan en varias plataformas.",
}

_PACKAGING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "description", "hashtags"],
}

_REPLY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reply": {"type": "string"},
        "grounded": {"type": "boolean"},
    },
    "required": ["reply", "grounded"],
}


def _clip(text: str, limit: int = 6000) -> str:
    return (text or "")[:limit]


def platform_packaging(
    router: Any, *, script: str, base_title: str, platform: str, program: str = "", language: str = "es"
) -> dict[str, Any]:
    """Título/descripción/hashtags adaptados a ``platform``, derivados del guion.
    Best-effort: si el modelo falla, devuelve un packaging mínimo honesto."""
    try:
        payload = router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(frozenset({"creative"}), structured_output=True),
            task="social.packaging",
            system=(
                "Eres el agente de empaquetado editorial de Kronara. A partir del GUION generas "
                "título, descripción y hashtags para UNA plataforma. Reglas: fieles al contenido "
                "del guion (no prometas lo que no ocurre); sin clickbait falso ni 'no creerás'; "
                "en el idioma indicado."
            ),
            input_payload={
                "language": language,
                "platform": platform,
                "platform_style": PLATFORM_STYLE.get(platform, PLATFORM_STYLE["aggregator"]),
                "program": program,
                "base_title": base_title,
                "script": _clip(script),
            },
            response_schema=_PACKAGING_SCHEMA,
            max_tokens=512,
        )
        return {
            "platform": platform,
            "title": str(payload.get("title") or base_title),
            "description": str(payload.get("description") or ""),
            "hashtags": [str(tag) for tag in payload.get("hashtags", ())][:8],
        }
    except Exception:
        return {"platform": platform, "title": base_title, "description": "", "hashtags": []}


def packaging_for_platforms(
    router: Any, *, script: str, base_title: str, platforms: "list[str]", program: str = "", language: str = "es"
) -> list[dict[str, Any]]:
    """Un packaging por plataforma solicitada (lo que el agente adjunta al publicar)."""
    return [
        platform_packaging(router, script=script, base_title=base_title, platform=p, program=program, language=language)
        for p in platforms
    ]


def draft_comment_reply(
    router: Any, *, script: str, comment: str, program: str = "", language: str = "es"
) -> dict[str, Any]:
    """Redacta una respuesta a un comentario ANCLADA en el guion. El agente sabe
    lo que hay gracias al guion; si el comentario pregunta algo que el guion no
    responde, lo dice con honestidad (grounded=False) en vez de inventar."""
    try:
        payload = router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(frozenset({"creative"}), structured_output=True),
            task="social.comment_reply",
            system=(
                "Eres el community manager de Kronara. Respondes comentarios usando SOLO lo que "
                "respalda el GUION del episodio. Tono cercano y breve. Si el comentario pregunta "
                "algo que el guion no dice, reconócelo con honestidad (no inventes); marca "
                "grounded=false en ese caso. Nunca reveles datos personales ni spoilers gratuitos."
            ),
            input_payload={"language": language, "program": program, "script": _clip(script), "comment": _clip(comment, 1000)},
            response_schema=_REPLY_SCHEMA,
            max_tokens=400,
        )
        return {"reply": str(payload.get("reply") or ""), "grounded": bool(payload.get("grounded", False))}
    except Exception:
        return {"reply": "", "grounded": False}
