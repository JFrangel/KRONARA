"""Hybrid visual source assignment -- decides, per shot, whether it draws
from AI-generated image (default), a stock video loop, or a recreated
graphic overlay (documents/messages, drawn with Pillow rather than SD, which
is not reliable for coherent text/UI).

Targets the product spec's 60-70% / 15-25% / 10-15% mix
(ai_image / video_loop / graphic_overlay). Assignment is deterministic --
a running-share ceiling per kind, never randomness -- so a given shot list
always assigns the same way and the resulting distribution is exactly
reproducible in tests. A shot is only moved off ai_image when a real signal
justifies it (narration mentions evidence/messages, or a matching library
clip actually exists) AND that kind is still under its target ceiling;
otherwise it falls back to ai_image ("no toma queda sin recurso").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from kronara.asset_library import AssetLibraryStore, LibraryAsset
from kronara.composition import Shot

# Upper bound of each kind's target share -- a ceiling that prevents a
# surplus of eligible shots from taking over the episode, not a floor to
# force-fill with content that doesn't actually warrant it.
VIDEO_LOOP_MAX_SHARE = 0.25
GRAPHIC_OVERLAY_MAX_SHARE = 0.15

_EVIDENCE_KEYWORDS = frozenset({
    "documento", "documentos", "mensaje", "mensajes", "carta", "cartas",
    "correo", "correos", "email", "emails", "captura", "capturas",
    "pantallazo", "pantallazos", "expediente", "expedientes", "informe",
    "informes", "contrato", "contratos", "factura", "facturas", "recibo",
    "recibos", "chat", "chats", "whatsapp", "nota", "notas",
})


@dataclass(frozen=True)
class ShotAssignment:
    shot_id: str
    source_kind: str  # "ai_image" | "video_loop" | "graphic_overlay"
    video_loop_asset: LibraryAsset | None = None


def mentions_evidence(text: str) -> bool:
    tokens = set(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))
    return bool(tokens & _EVIDENCE_KEYWORDS)


def assign_visual_sources(
    shots: Sequence[Shot],
    scene_texts: Mapping[str, str],
    *,
    library: AssetLibraryStore | None = None,
    asset_tags: Sequence[str] = (),
) -> tuple[ShotAssignment, ...]:
    total = len(shots)
    # Fixed budgets against the known total, not a running share of shots
    # processed so far -- a running-share check is unstable early on (the
    # first admission is always "100% of shots seen") and systematically
    # overshoots the cap by the time the denominator catches up. Floored
    # (not rounded) and floored-at-1: a short scene with a clear, specific
    # signal (an evidence beat, a matching clip) should still get to use it
    # even when cap_fraction * total rounds under one whole shot.
    overlay_budget = max(1, int(GRAPHIC_OVERLAY_MAX_SHARE * total))
    video_budget = max(1, int(VIDEO_LOOP_MAX_SHARE * total))

    counts = {"ai_image": 0, "video_loop": 0, "graphic_overlay": 0}
    assignments: list[ShotAssignment] = []

    for shot in shots:
        text = scene_texts.get(shot.scene_id, "")
        video_candidate = _find_video_loop(library, asset_tags)

        if mentions_evidence(text) and counts["graphic_overlay"] + 1 <= overlay_budget:
            kind, asset = "graphic_overlay", None
        elif video_candidate is not None and counts["video_loop"] + 1 <= video_budget:
            kind, asset = "video_loop", video_candidate
            library.mark_used(asset.asset_id)  # type: ignore[union-attr]
        else:
            kind, asset = "ai_image", None

        counts[kind] += 1
        assignments.append(ShotAssignment(shot.shot_id, kind, asset))

    return tuple(assignments)


def _find_video_loop(
    library: AssetLibraryStore | None, asset_tags: Sequence[str]
) -> LibraryAsset | None:
    if library is None or not asset_tags:
        return None
    for tag in asset_tags:
        candidates = library.by_tag("video_loop", tag, limit=1)
        if candidates:
            return candidates[0]
    return None
