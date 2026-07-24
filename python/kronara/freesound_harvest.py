"""Cosechador de música/SFX CC0 desde Freesound para poblar la biblioteca (V7).

Amplía la ambientación (moods de música y tags de SFX) con audio de dominio
público (CC0). Espeja a pexels_harvest: el buscador y el descargador se INYECTAN
-> tests herméticos sin red. En producción, los adaptadores usan la API de
Freesound con el token OAuth2 (KRONARA_FREESOUND_ACCESS_TOKEN, expira 24h).

El script standalone scripts/harvest_freesound.py hace lo mismo por CLI; este
módulo es el core reutilizable para exponerlo también como RPC desde la UI.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from kronara.asset_library import AssetLibraryStore, LibraryAsset
from kronara.audio_mix import DEFAULT_KEYWORD_SFX

CC0_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"

MUSIC_QUERIES = {
    "paranormal-tension": "dark tension drone horror",
    "dramatico-emocional": "emotional piano sad cinematic",
    "venganza-triunfal": "victory fanfare",
    "confesion-intimo": "intimate ambient soft piano",
    "misterio-investigativo": "mystery ambient tension",
    "documental-serio": "procedural ambient drone",
}
SFX_QUERIES = {tag: tag.replace("_", " ") for tag in sorted(set(DEFAULT_KEYWORD_SFX.values()))}
SFX_QUERIES.update({
    "door_creak": "door creak wood",
    "footsteps": "footsteps wood floor",
    "wind": "wind howl",
    "phone_ring": "phone ring old",
    "page_turn": "page turn book",
    "static": "radio static noise",
})


@dataclass(frozen=True)
class HarvestReport:
    tag: str
    status: str  # "seeded" | "duplicate" | "no_result" | "error"
    detail: str = ""


def freesound_search(token: str) -> Callable[[str, float, float], "dict[str, Any] | None"]:
    def _search(query: str, min_duration: float, max_duration: float) -> "dict[str, Any] | None":
        params = urllib.parse.urlencode({
            "query": query,
            "filter": f'license:"Creative Commons 0" duration:[{min_duration} TO {max_duration}]',
            "fields": "id,name,license,duration,username,url",
            "page_size": 5,
            "sort": "score",
        })
        request = urllib.request.Request(
            f"https://freesound.org/apiv2/search/text/?{params}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            results = json.loads(response.read().decode()).get("results", [])
        return results[0] if results else None

    return _search


def freesound_download(token: str) -> Callable[[int, Path], str]:
    def _download(sound_id: int, dest_stem: Path) -> str:
        request = urllib.request.Request(
            f"https://freesound.org/apiv2/sounds/{sound_id}/download/",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            disposition = response.headers.get("Content-Disposition", "")
            data = response.read()
        extension = "." + disposition.rsplit(".", 1)[-1].strip('"; \n') if "." in disposition else ".wav"
        final = Path(dest_stem).with_suffix(extension)
        final.write_bytes(data)
        return str(final)

    return _download


def harvest_freesound(
    *,
    search: Callable[[str, float, float], "dict[str, Any] | None"],
    download: Callable[[int, Path], str],
    library: AssetLibraryStore,
    queries: "dict[str, str]",
    asset_type: str,
    dest_dir: "str | Path",
    min_duration: float,
    max_duration: float,
    now: int = 0,
) -> dict[str, Any]:
    """Por cada (tag, query): busca el mejor CC0 en banda de duración -> descarga
    -> siembra. Idempotente (dedup por file_path); un tag sin resultado/error no
    corta el resto. Devuelve {seeded, reports}."""
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    reports: list[HarvestReport] = []
    seeded = 0
    for tag, query in queries.items():
        try:
            hit = search(query, min_duration, max_duration)
            if not hit:
                reports.append(HarvestReport(tag, "no_result"))
                continue
            path = download(int(hit["id"]), Path(dest_dir) / f"{tag}_{hit['id']}")
            asset = LibraryAsset(
                asset_type=asset_type,
                tags=(tag,),
                file_path=path,
                duration_ms=int(float(hit.get("duration", 0)) * 1000),
                rights_mode="cc0",
                attribution_text=f"{hit.get('name', '')} by {hit.get('username', '')} (Freesound)".strip(),
                license_url=CC0_LICENSE_URL,
                source_url=str(hit.get("url", "")),
                added_at=int(now),
            )
            if library.seed(asset):
                seeded += 1
                reports.append(HarvestReport(tag, "seeded", path))
            else:
                reports.append(HarvestReport(tag, "duplicate", path))
        except Exception as error:  # noqa: BLE001 - un tag no debe tumbar la cosecha
            reports.append(HarvestReport(tag, "error", type(error).__name__))
    return {"seeded": seeded, "reports": [asdict(report) for report in reports]}
