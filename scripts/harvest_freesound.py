"""Curate real CC0 music/SFX from Freesound and seed AssetLibraryStore.

Manual/scheduled script (matches harvest_reddit.py's pattern) -- not part of
the hot autonomous path. Searches one query per program mood (music) and per
SFX keyword tag, filtered to license:"Creative Commons 0", downloads the top
match via the OAuth2 download endpoint, and seeds it into the shared asset
library with full rights metadata.

Requires a completed Freesound OAuth2 authorization: KRONARA_FREESOUND_
ACCESS_TOKEN in .env (see docs/roadmap for the authorize-code exchange flow).
Access tokens expire in 24h; re-run the exchange with the refresh_token when
this starts failing with 401s (not yet automated here -- a good next step if
this becomes a recurring job).

Usage: python scripts/harvest_freesound.py [music|sfx]   (omit to run both)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from kronara.asset_library import AssetLibraryStore, LibraryAsset  # noqa: E402
from kronara.audio_mix import DEFAULT_KEYWORD_SFX  # noqa: E402

MUSIC_DIR = ROOT / ".kronara" / "assets" / "music"
SFX_DIR = ROOT / ".kronara" / "assets" / "sfx"
LIBRARY_DB = ROOT / ".kronara" / "asset_library.db"

# One search query per program mood (config/programs/visual_style.v1.json's
# music_moods vocabulary) and per SFX tag (audio_mix.DEFAULT_KEYWORD_SFX's
# values) -- broadened by hand where the obvious query returned zero CC0
# hits in the min/max duration band during initial curation.
MUSIC_QUERIES = {
    "paranormal-tension": "dark tension drone horror",
    "dramatico-emocional": "emotional piano sad cinematic",
    "venganza-triunfal": "victory fanfare",
    "confesion-intimo": "intimate ambient soft piano",
    "misterio-investigativo": "mystery ambient tension",
    "documental-serio": "procedural ambient drone",
}
SFX_QUERIES = {tag: tag.replace("_", " ") for tag in sorted(set(DEFAULT_KEYWORD_SFX.values()))}
# A couple of tags read better with a more specific query than their bare name.
SFX_QUERIES.update({
    "door_creak": "door creak wood",
    "footsteps": "footsteps wood floor",
    "wind": "wind howl",
    "phone_ring": "phone ring old",
    "page_turn": "page turn book",
    "static": "radio static noise",
})


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    with open(ROOT / ".env", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def _api_get(path: str, token: str, **params) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"https://freesound.org/apiv2/{path}?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def _download(sound_id: int, token: str, dest_stem: Path) -> str:
    request = urllib.request.Request(
        f"https://freesound.org/apiv2/sounds/{sound_id}/download/",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        disposition = response.headers.get("Content-Disposition", "")
        data = response.read()
    extension = "." + disposition.rsplit(".", 1)[-1].strip('"; \n') if "." in disposition else ".wav"
    final_path = dest_stem.with_suffix(extension)
    final_path.write_bytes(data)
    return str(final_path)


def search_best(query: str, token: str, *, min_duration: float, max_duration: float) -> dict | None:
    result = _api_get(
        "search/text/", token,
        query=query,
        filter=f'license:"Creative Commons 0" duration:[{min_duration} TO {max_duration}]',
        fields="id,name,license,duration,username,url",
        page_size=5,
        sort="score",
    )
    results = result.get("results", [])
    return results[0] if results else None


def _curate(
    queries: dict[str, str], *, asset_type: str, dest_dir: Path, min_duration: float,
    max_duration: float, token: str, library: AssetLibraryStore,
) -> list[tuple[str, str, str | None]]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    report: list[tuple[str, str, str | None]] = []
    for tag, query in queries.items():
        try:
            hit = search_best(query, token, min_duration=min_duration, max_duration=max_duration)
            if not hit:
                report.append((tag, "NO_RESULT", None))
                continue
            path = _download(hit["id"], token, dest_dir / f"{tag}_{hit['id']}")
            added = library.seed(LibraryAsset(
                asset_type=asset_type, tags=(tag,), file_path=path,
                duration_ms=int(hit["duration"] * 1000), rights_mode="cc0",
                attribution_text=f"{hit['name']} by {hit['username']} (Freesound)",
                license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                source_url=hit["url"], added_at=now,
            ))
            report.append((tag, "OK" if added else "DUPLICATE", hit["name"]))
            time.sleep(1)  # be polite to the API
        except urllib.error.HTTPError as error:
            report.append((tag, f"HTTP_{error.code}", error.read().decode()[:200]))
    return report


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else None
    env = _load_env()
    token = env.get("KRONARA_FREESOUND_ACCESS_TOKEN")
    if not token:
        print("KRONARA_FREESOUND_ACCESS_TOKEN is not set in .env -- complete the OAuth2 authorize step first.")
        return 1

    library = AssetLibraryStore(LIBRARY_DB).initialize()
    report: list[tuple[str, str, str | None]] = []
    if which in (None, "music"):
        report += _curate(
            MUSIC_QUERIES, asset_type="music", dest_dir=MUSIC_DIR,
            min_duration=20, max_duration=300, token=token, library=library,
        )
    if which in (None, "sfx"):
        report += _curate(
            SFX_QUERIES, asset_type="sfx", dest_dir=SFX_DIR,
            min_duration=0.1, max_duration=6, token=token, library=library,
        )
    library.close()

    print(f"\n{'tag':<25} {'status':<12} name")
    for tag, status, name in report:
        print(f"{tag:<25} {status:<12} {name or ''}")
    ok = sum(1 for _, status, _ in report if status == "OK")
    print(f"\n{ok}/{len(report)} assets seeded")
    return 0 if ok == len(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
