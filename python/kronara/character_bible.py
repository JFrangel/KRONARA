"""Per-episode character "bible": one short canonical appearance description per
recurring character, so every scene renders the SAME person (v0.8, cross-scene
visual consistency -- docs/CONSISTENCIA_ESCENAS.md #3).

Named characters otherwise get a fresh face each shot on hosted Flux providers
(Pollinations/Cloudflare) because those ignore reference images -- the appearance
TEXT is the primary consistency lever there. This makes ONE cheap structured
model call up front and injects the descriptions into every scene's image prompt.

Best-effort by contract: any failure (no model quota, bad JSON) returns an empty
bible and the video still renders with the prior name+"same faces" text anchors.
"""

from __future__ import annotations

from kronara.model_registry_v2 import ModelRequirements

_BIBLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["characters"],
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "appearance"],
                "properties": {
                    "name": {"type": "string"},
                    "appearance": {"type": "string"},
                },
            },
        }
    },
}

_BIBLE_SYSTEM = (
    "Eres director de casting visual. Para CADA personaje entrega UNA descripción "
    "física concisa y concreta (edad aproximada, complexión, rasgos, pelo, "
    "vestuario típico) coherente con la historia, pensada para que un generador "
    "de imágenes mantenga la MISMA apariencia en todas las escenas. Español. "
    "No uses nombres de personas reales ni de famosos; describe rasgos, no marcas."
)


def build_character_bible(
    router,
    *,
    character_names,
    premise: str = "",
    theme: str = "",
    program_id: str | None = None,
    language: str = "es",
) -> dict[str, str]:
    """Return ``{casefolded_name: appearance_description}`` for the given
    characters via one structured model call. Empty dict on any failure."""
    names = [str(name).strip() for name in character_names if str(name).strip()]
    if not names:
        return {}
    try:
        payload = router.complete(
            alias="creative_primary",
            requirements=ModelRequirements(frozenset({"creative"}), structured_output=True),
            task="story.character_bible",
            system=_BIBLE_SYSTEM,
            input_payload={
                "premise": premise,
                "theme": theme,
                "characters": names,
                "program_id": program_id or "",
                "language": language,
            },
            response_schema=_BIBLE_SCHEMA,
            max_tokens=700,
        )
    except Exception:
        return {}
    bible: dict[str, str] = {}
    items = payload.get("characters", []) if isinstance(payload, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        appearance = str(item.get("appearance", "")).strip()
        if name and appearance:
            bible[name.casefold()] = appearance
    return bible
