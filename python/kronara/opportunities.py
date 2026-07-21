"""Harvested opportunity queue + anti-repetition ledger.

Two durable stores so the agent can work across iterations:

- ``OpportunityStore``: one run reads several subreddits and *saves* the
  harvested posts (titles = abstract seeds). Later iterations pull unused ones
  one at a time — which also means Reddit is read in bulk occasionally instead
  of on every run (kinder to rate limits). De-duplicated by content hash.

- ``StoryLedger``: records a signature of every produced story so the agent does
  not create the same story twice ("be authentic"). It is **series-aware**: a
  later part of the *same* serialized story is never treated as a repeat, so
  multi-part continuity is preserved.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "you", "your", "was", "are",
    "his", "her", "she", "him", "they", "them", "not", "but", "have", "had",
    "que", "los", "las", "una", "uno", "por", "con", "del", "para", "como",
    "mi", "su", "sus", "lo", "le", "de", "el", "la", "en", "un", "se", "es",
    "al", "me", "te", "ya", "yo", "he", "ha",
}


def signature_tokens(text: str) -> frozenset[str]:
    """Meaningful lowercase tokens (>=4 chars, non-stopword) for similarity."""
    tokens = re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
    return frozenset(t for t in tokens if len(t) >= 4 and t not in _STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    subreddit: str
    theme_hint: str
    link: str
    harvested_at: int
    status: str
    # "entertainment" | "real_experience_serious" — see knowledge/reddit-sources/.
    sensitivity: str = "entertainment"


def _opportunity_id(subreddit: str, title: str) -> str:
    return hashlib.sha256(f"{subreddit}|{title}".encode("utf-8")).hexdigest()[:16]


class OpportunityStore:
    def __init__(self, database: Path | str):
        self.database = Path(database) if database != ":memory:" else ":memory:"
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> "OpportunityStore":
        if self.database != ":memory:":
            self.database.parent.mkdir(parents=True, exist_ok=True)
        self._conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS opportunities (
                opportunity_id TEXT PRIMARY KEY,
                subreddit TEXT NOT NULL,
                theme_hint TEXT NOT NULL,
                link TEXT NOT NULL,
                harvested_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                sensitivity TEXT NOT NULL DEFAULT 'entertainment'
            );
            CREATE INDEX IF NOT EXISTS idx_oppo_status ON opportunities(status);
            """
        )
        try:  # migration for a pre-existing local db created before this column
            self._conn().execute(
                "ALTER TABLE opportunities ADD COLUMN sensitivity TEXT NOT NULL DEFAULT 'entertainment'"
            )
        except sqlite3.OperationalError:
            pass  # column already present
        self._conn().commit()
        return self

    def harvest(self, posts, now: int) -> int:
        """Save new posts (dedup by content hash); returns how many were new."""
        connection = self._conn()
        added = 0
        for post in posts:
            subreddit = getattr(post, "subreddit", "")
            title = getattr(post, "title", "")
            link = getattr(post, "link", "")
            sensitivity = getattr(post, "sensitivity", "entertainment") or "entertainment"
            if not title:
                continue
            oid = _opportunity_id(subreddit, title)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO opportunities
                    (opportunity_id, subreddit, theme_hint, link, harvested_at, status, sensitivity)
                VALUES (?, ?, ?, ?, ?, 'new', ?)
                """,
                (oid, subreddit, title, link, now, sensitivity),
            )
            added += cursor.rowcount
        connection.commit()
        return added

    def pending(self, limit: int = 20) -> list[Opportunity]:
        rows = self._conn().execute(
            "SELECT * FROM opportunities WHERE status='new' ORDER BY harvested_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row(row) for row in rows]

    def take_next(self, now: int) -> Opportunity | None:
        """Return the oldest unused opportunity and mark it used (anti-repeat)."""
        row = self._conn().execute(
            "SELECT * FROM opportunities WHERE status='new' ORDER BY harvested_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self._conn().execute(
            "UPDATE opportunities SET status='used' WHERE opportunity_id=?",
            (row["opportunity_id"],),
        )
        self._conn().commit()
        used = dict(row)
        used["status"] = "used"
        return self._row(used)

    def take_next_for_subreddits(self, subreddits: Iterable[str], now: int) -> Opportunity | None:
        """Like take_next(), scoped to one program's own subreddit pool (its
        F0 nodo-<program_id>.md list) -- content.run should draw a program's
        episode from the sources actually curated for it, not from whatever
        other program's backlog happens to be oldest in a shared queue."""
        names = [str(item) for item in subreddits]
        if not names:
            return None
        placeholders = ",".join("?" for _ in names)
        row = self._conn().execute(
            f"SELECT * FROM opportunities WHERE status='new' AND subreddit IN ({placeholders}) "
            "ORDER BY harvested_at ASC LIMIT 1",
            names,
        ).fetchone()
        if row is None:
            return None
        self._conn().execute(
            "UPDATE opportunities SET status='used' WHERE opportunity_id=?",
            (row["opportunity_id"],),
        )
        self._conn().commit()
        used = dict(row)
        used["status"] = "used"
        return self._row(used)

    def count(self, status: str | None = None) -> int:
        if status is None:
            row = self._conn().execute("SELECT COUNT(*) AS n FROM opportunities").fetchone()
        else:
            row = self._conn().execute(
                "SELECT COUNT(*) AS n FROM opportunities WHERE status=?", (status,)
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
    def _row(row) -> Opportunity:
        keys = row.keys() if hasattr(row, "keys") else row
        return Opportunity(
            opportunity_id=row["opportunity_id"],
            subreddit=row["subreddit"],
            theme_hint=row["theme_hint"],
            link=row["link"],
            harvested_at=row["harvested_at"],
            status=row["status"],
            sensitivity=row["sensitivity"] if "sensitivity" in keys else "entertainment",
        )


class StoryLedger:
    """Records produced-story signatures to prevent near-duplicate stories.

    Series-aware: a new story is only a repeat of a *different* series. Later
    parts of the same series (same ``series_id``) are always allowed.
    """

    def __init__(self, database: Path | str, *, threshold: float = 0.7):
        self.database = Path(database) if database != ":memory:" else ":memory:"
        self.threshold = threshold
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> "StoryLedger":
        if self.database != ":memory:":
            self.database.parent.mkdir(parents=True, exist_ok=True)
        self._conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS story_ledger (
                story_id TEXT PRIMARY KEY,
                series_id TEXT,
                tokens TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )
        self._conn().commit()
        return self

    def is_repeat(self, text: str, *, series_id: str | None = None) -> bool:
        tokens = signature_tokens(text)
        for row in self._conn().execute(
            "SELECT series_id, tokens FROM story_ledger"
        ).fetchall():
            # Same series => a legitimate continuation, never a repeat.
            if series_id is not None and row["series_id"] == series_id:
                continue
            stored = frozenset(row["tokens"].split())
            if jaccard(tokens, stored) >= self.threshold:
                return True
        return False

    def record(self, story_id: str, text: str, *, series_id: str | None, now: int) -> None:
        tokens = " ".join(sorted(signature_tokens(text)))
        self._conn().execute(
            """
            INSERT INTO story_ledger (story_id, series_id, tokens, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(story_id) DO UPDATE SET
                series_id=excluded.series_id, tokens=excluded.tokens, created_at=excluded.created_at
            """,
            (story_id, series_id, tokens, now),
        )
        self._conn().commit()

    def count(self) -> int:
        return int(self._conn().execute("SELECT COUNT(*) AS n FROM story_ledger").fetchone()["n"])

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
