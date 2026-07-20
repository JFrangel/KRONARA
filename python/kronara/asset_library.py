"""Shared library for music/SFX/video-loop assets — same harvest-once,
dispense-many SQLite pattern as ``OpportunityStore``, adapted for reuse
semantics: a track is never "consumed" (unlike an opportunity), it is
dispensed repeatedly across many episodes, so this store tracks a use_count
for fair rotation instead of a used/new status flag.

One store serves all three asset kinds (``music``, ``sfx``, ``video_loop``)
because they share the same lifecycle: manually curated or harvested once
(V4 music, V5 SFX, V7 Pexels/Freesound), tagged by mood/keyword, then
dispensed by tag whenever a scene needs one. Every row carries its rights
metadata (``rights_mode``/``attribution_text``/``license_url``/``source_url``)
so nothing is ever mixed into a render without a recorded license.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ASSET_TYPES = frozenset({"music", "sfx", "video_loop"})


@dataclass(frozen=True)
class LibraryAsset:
    asset_type: str
    tags: tuple[str, ...]
    file_path: str
    duration_ms: int
    rights_mode: str
    attribution_text: str = ""
    license_url: str = ""
    source_url: str = ""
    added_at: int = 0
    use_count: int = 0
    # Left blank by curators constructing a new asset -- seed() derives it
    # deterministically from (asset_type, file_path); always populated when
    # a LibraryAsset is read back from the store.
    asset_id: str = ""


def _asset_id(asset_type: str, file_path: str) -> str:
    return hashlib.sha256(f"{asset_type}|{file_path}".encode("utf-8")).hexdigest()[:16]


class AssetLibraryStore:
    def __init__(self, database: Path | str):
        self.database = Path(database) if database != ":memory:" else ":memory:"
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> "AssetLibraryStore":
        if self.database != ":memory:":
            self.database.parent.mkdir(parents=True, exist_ok=True)
        self._conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                asset_type TEXT NOT NULL,
                tags TEXT NOT NULL,
                file_path TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                rights_mode TEXT NOT NULL,
                attribution_text TEXT NOT NULL DEFAULT '',
                license_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                added_at INTEGER NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
            """
        )
        self._conn().commit()
        return self

    def seed(self, asset: LibraryAsset) -> bool:
        """Insert an asset (dedup by type+file_path); returns True if newly added."""
        if asset.asset_type not in ASSET_TYPES:
            raise ValueError(f"unknown asset_type: {asset.asset_type}")
        if not asset.rights_mode:
            raise ValueError("rights_mode is required")
        asset_id = asset.asset_id or _asset_id(asset.asset_type, asset.file_path)
        cursor = self._conn().execute(
            """
            INSERT OR IGNORE INTO assets
                (asset_id, asset_type, tags, file_path, duration_ms, rights_mode,
                 attribution_text, license_url, source_url, added_at, use_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                asset_id, asset.asset_type, ",".join(asset.tags), asset.file_path,
                asset.duration_ms, asset.rights_mode, asset.attribution_text,
                asset.license_url, asset.source_url, asset.added_at,
            ),
        )
        self._conn().commit()
        return cursor.rowcount > 0

    def by_tag(self, asset_type: str, tag: str, limit: int = 5) -> list[LibraryAsset]:
        """Assets of a type carrying the given tag, least-used first so
        repeated dispensing rotates fairly across the library instead of
        always returning the same first match."""
        rows = self._conn().execute(
            "SELECT * FROM assets WHERE asset_type=? AND (',' || tags || ',') LIKE ? "
            "ORDER BY use_count ASC, added_at ASC LIMIT ?",
            (asset_type, f"%,{tag},%", limit),
        ).fetchall()
        return [self._row(row) for row in rows]

    def mark_used(self, asset_id: str) -> None:
        self._conn().execute(
            "UPDATE assets SET use_count = use_count + 1 WHERE asset_id=?", (asset_id,)
        )
        self._conn().commit()

    def count(self, asset_type: str | None = None) -> int:
        if asset_type is None:
            row = self._conn().execute("SELECT COUNT(*) AS n FROM assets").fetchone()
        else:
            row = self._conn().execute(
                "SELECT COUNT(*) AS n FROM assets WHERE asset_type=?", (asset_type,)
            ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            target = self.database if self.database == ":memory:" else str(self.database)
            self._connection = sqlite3.connect(target)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @staticmethod
    def _row(row) -> LibraryAsset:
        tags = tuple(t for t in row["tags"].split(",") if t)
        return LibraryAsset(
            asset_id=row["asset_id"],
            asset_type=row["asset_type"],
            tags=tags,
            file_path=row["file_path"],
            duration_ms=row["duration_ms"],
            rights_mode=row["rights_mode"],
            attribution_text=row["attribution_text"],
            license_url=row["license_url"],
            source_url=row["source_url"],
            added_at=row["added_at"],
            use_count=row["use_count"],
        )


def sfx_paths_from_library(library: AssetLibraryStore, tags: Iterable[str]) -> dict[str, str]:
    """Resolve one file path per SFX tag from the library -- the adapter
    between AssetLibraryStore and render_composition()'s `sfx_paths: dict[tag,
    path]` argument. Marks each resolved asset used (fair rotation across
    episodes). A tag with no library asset yet is silently omitted: render.py
    already treats a cue with no matching sfx_paths entry as a soft skip
    (match_sfx_cues found the cue in the narration, but there's nothing to
    play for it yet), never an error."""
    resolved: dict[str, str] = {}
    for tag in tags:
        candidates = library.by_tag("sfx", tag, limit=1)
        if not candidates:
            continue
        asset = candidates[0]
        library.mark_used(asset.asset_id)
        resolved[tag] = asset.file_path
    return resolved
