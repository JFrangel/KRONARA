"""Curate real b-roll video clips from Pexels and seed AssetLibraryStore.

Manual/scheduled script (matches harvest_freesound.py's pattern) -- not part
of the hot autonomous path. Pexels' API key is a static bearer token (no
OAuth exchange), so -- like Freesound's curation script -- this calls the
Pexels HTTP API directly rather than through the Rust authority plane; the
Rust pexels.rs authority module (and its "pexels.search_videos" entry in
both ALLOWED_AUTHORITY_TOOLS allowlists) remains available for a future
live/on-demand fetch during autonomous production, but pre-curating a fixed
library is enough to give visual_director.py's "video_loop" tier real
content to draw from today.

Searches one query per unique asset_tag across every program in
config/programs/visual_style.v1.json, restricted to portrait-oriented
source clips (Kronara's programs render 9:16). Downloads the "hd" mp4
file when available (mirrors select_video_file() in pexels.rs), preferring
a reasonably short clip among the results so video_clip_filter() doesn't
have to trim much.

Requires KRONARA_PEXELS_API_KEY in .env (see docs/roadmap; free tier is
200 requests/hour, 20,000/month).

Usage: python scripts/harvest_pexels.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from kronara.asset_library import AssetLibraryStore, LibraryAsset  # noqa: E402

VIDEO_DIR = ROOT / ".kronara" / "assets" / "video_loop"
LIBRARY_DB = ROOT / ".kronara" / "asset_library.db"
VISUAL_STYLE_PATH = ROOT / "config" / "programs" / "visual_style.v1.json"

API_ROOT = "https://api.pexels.com/videos/search"
PER_PAGE = 5
PREFERRED_MAX_DURATION = 40  # seconds -- prefer shorter clips when available
MIN_DURATION = 3  # seconds -- discard near-instant clips that won't cover a shot

# Pexels sits behind Cloudflare, which bot-fight-mode-blocks urllib's default
# "Python-urllib/x.y" user agent with a 403 (Cloudflare error 1010) before the
# request ever reaches Pexels' own auth check. A browser-shaped UA clears it.
_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


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


def _unique_asset_tags() -> list[str]:
    data = json.loads(VISUAL_STYLE_PATH.read_text(encoding="utf-8"))
    seen: dict[str, None] = {}
    for program in data["programs"]:
        for tag in program["asset_tags"]:
            seen.setdefault(tag, None)
    return list(seen)


def _search(query: str, api_key: str) -> dict:
    params = urllib.parse.urlencode({"query": query, "per_page": PER_PAGE, "orientation": "portrait"})
    request = urllib.request.Request(
        f"{API_ROOT}?{params}",
        headers={**_REQUEST_HEADERS, "Authorization": api_key},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def _select_file(video: dict) -> tuple[str, int, int] | None:
    """Mirrors select_video_file() in pexels.rs: prefer the "hd" mp4, else
    the first mp4 present. Returns (download_url, width, height) or None."""
    mp4_files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
    if not mp4_files:
        return None
    hd = next((f for f in mp4_files if f.get("quality") == "hd"), None)
    chosen = hd or mp4_files[0]
    return chosen["link"], chosen.get("width", 0), chosen.get("height", 0)


def _select_video(videos: list[dict]) -> dict | None:
    """Prefer a result within the preferred duration band; fall back to the
    first usable result otherwise (soft preference, not a hard filter)."""
    in_band = [v for v in videos if MIN_DURATION <= v.get("duration", 0) <= PREFERRED_MAX_DURATION]
    for candidate in in_band + videos:
        if _select_file(candidate) is not None:
            return candidate
    return None


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers=_REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.write_bytes(response.read())


def _curate(tags: list[str], *, api_key: str, library: AssetLibraryStore) -> list[tuple[str, str, str | None]]:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    report: list[tuple[str, str, str | None]] = []
    for tag in tags:
        query = tag.replace("-", " ")
        try:
            payload = _search(query, api_key)
            video = _select_video(payload.get("videos", []))
            if video is None:
                report.append((tag, "NO_RESULT", None))
                continue
            download_url, width, height = _select_file(video)
            dest = VIDEO_DIR / f"{tag}_{video['id']}.mp4"
            _download(download_url, dest)
            added = library.seed(LibraryAsset(
                asset_type="video_loop", tags=(tag,), file_path=str(dest),
                duration_ms=int(video.get("duration", 0) * 1000), rights_mode="pexels_license",
                attribution_text=f"Video by {video.get('user', {}).get('name', 'unknown')} (Pexels)",
                license_url="https://www.pexels.com/license/",
                source_url=video.get("url", ""), added_at=now,
            ))
            report.append((tag, "OK" if added else "DUPLICATE", f"{width}x{height} {video.get('duration')}s"))
            time.sleep(1)  # be polite to the API
        except urllib.error.HTTPError as error:
            report.append((tag, f"HTTP_{error.code}", error.read().decode()[:200]))
    return report


def main() -> int:
    env = _load_env()
    api_key = env.get("KRONARA_PEXELS_API_KEY")
    if not api_key:
        print("KRONARA_PEXELS_API_KEY is not set in .env.")
        return 1

    tags = _unique_asset_tags()
    library = AssetLibraryStore(LIBRARY_DB).initialize()
    report = _curate(tags, api_key=api_key, library=library)
    library.close()

    print(f"\n{'tag':<24} {'status':<12} detail")
    for tag, status, detail in report:
        print(f"{tag:<24} {status:<12} {detail or ''}")
    ok = sum(1 for _, status, _ in report if status == "OK")
    print(f"\n{ok}/{len(report)} assets seeded")
    return 0 if ok == len(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
