"""Cosechador de video-loops de Pexels para poblar la biblioteca (V7 real).

Da metraje REAL en movimiento a las escenas (fuente ``video_loop``, que la
composición ya sabe renderizar con ``-stream_loop -1`` + ``video_clip_filter``):
por cada tag (mood/escena) busca clips verticales, elige uno en banda de
duración, descarga el MP4 y lo siembra como asset ``video_loop`` con su licencia.

El buscador y el descargador se INYECTAN -> los tests corren sin red. En
producción, el buscador va por la autoridad Node (``pexels.search_videos``) que
custodia la API key; el script standalone puede pasar un buscador HTTP directo.

Pexels License: uso libre, atribución recomendada. Cada fila registra
``rights_mode='pexels_license'`` + ``license_url`` + ``source_url``.
"""

from __future__ import annotations

import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from kronara.asset_library import AssetLibraryStore, LibraryAsset

PEXELS_LICENSE_URL = "https://www.pexels.com/license/"

# Tags atmosféricos por defecto (moods de los programas): terror/misterio/urbano/
# naturaleza. El caller puede pasar su propia lista (p.ej. de los estilos).
DEFAULT_VIDEO_LOOP_TAGS = (
    "night", "rain", "fog", "forest", "city", "corridor",
    "ocean", "storm", "candle", "shadow",
)


@dataclass(frozen=True)
class HarvestReport:
    tag: str
    status: str  # "seeded" | "duplicate" | "no_result" | "error"
    detail: str = ""


def _default_download(url: str, dest: str) -> None:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - pexels CDN
        Path(dest).write_bytes(response.read())


def select_video(videos: list[dict[str, Any]], *, min_s: int = 4, max_s: int = 40) -> dict[str, Any] | None:
    """Elige el mejor clip: prioriza duración dentro de banda [min,max] y, dentro
    de eso, la más cercana a ~12s (buena para loopear bajo una escena)."""
    usable = [v for v in videos if v.get("download_url")]
    if not usable:
        return None

    def score(video: dict[str, Any]) -> tuple[int, int]:
        seconds = int(float(video.get("duration_seconds") or 0))
        in_band = 1 if min_s <= seconds <= max_s else 0
        return (in_band, -abs(seconds - 12))

    return max(usable, key=score)


def authority_search(authority: Any, *, per_page: int = 5) -> Callable[[str], dict[str, Any]]:
    """Adaptador de producción: busca vía la autoridad Node (que tiene la key)."""

    def _search(query: str) -> dict[str, Any]:
        return authority.invoke(
            "pexels.search_videos",
            {"schema_version": 1, "query": query, "orientation": "portrait", "per_page": per_page, "page": 1},
        )

    return _search


def harvest_video_loops(
    *,
    search: Callable[[str], dict[str, Any]],
    library: AssetLibraryStore,
    tags: "tuple[str, ...] | list[str]",
    video_dir: "str | Path",
    download: Callable[[str, str], None] | None = None,
    now: int = 0,
) -> dict[str, Any]:
    """Por cada tag: busca -> elige -> descarga -> siembra video_loop. Idempotente
    (dedup por file_path en seed()); un tag sin resultados o con error no corta el
    resto. Devuelve {seeded, reports}."""
    download = download or _default_download
    Path(video_dir).mkdir(parents=True, exist_ok=True)
    reports: list[HarvestReport] = []
    seeded = 0
    for tag in tags:
        try:
            page = search(tag) or {}
            video = select_video(list(page.get("videos") or []))
            if video is None:
                reports.append(HarvestReport(tag, "no_result"))
                continue
            source_id = str(video.get("source_id") or "")
            dest = str(Path(video_dir) / f"{tag}_{source_id}.mp4")
            asset = LibraryAsset(
                asset_type="video_loop",
                tags=(tag,),
                file_path=dest,
                duration_ms=int(float(video.get("duration_seconds") or 0) * 1000),
                rights_mode="pexels_license",
                attribution_text=f"Pexels / {video.get('photographer', '')}".strip(" /"),
                license_url=PEXELS_LICENSE_URL,
                source_url=str(video.get("source_uri") or video.get("download_url") or ""),
                added_at=int(now),
            )
            if not Path(dest).exists():
                download(str(video.get("download_url") or ""), dest)
            if library.seed(asset):
                seeded += 1
                reports.append(HarvestReport(tag, "seeded", dest))
            else:
                reports.append(HarvestReport(tag, "duplicate", dest))
        except Exception as error:  # noqa: BLE001 - un tag no debe tumbar la cosecha
            reports.append(HarvestReport(tag, "error", type(error).__name__))
    return {"seeded": seeded, "reports": [asdict(report) for report in reports]}
