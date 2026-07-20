"""Harvest story opportunities from Reddit RSS (no credentials) and save them.

One run reads several target subreddits via public RSS (no app, no login, no
password), de-duplicates against what is already stored, and persists the new
posts so later iterations can adapt them without re-hitting Reddit. Reddit
rate-limits these feeds, so it reads a couple of subs per run with backoff.

Usage: python scripts/harvest_reddit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from kronara.opportunities import OpportunityStore  # noqa: E402
from kronara.reddit_rss import RedditRssReader  # noqa: E402

TARGET_SUBREDDITS = [
    "ProRevenge",
    "AmItheAsshole",
    "TrueScaryStories",
    "confessions",
    "relationship_advice",
    "MaliciousCompliance",
]

# Deterministic-ish timestamp source without a wall clock in the demo.
_NOW = 1_800_000_000


def main() -> int:
    db = Path(__file__).resolve().parents[1] / ".kronara" / "opportunities.db"
    store = OpportunityStore(db).initialize()
    reader = RedditRssReader(user_agent="windows:kronara45:v0.6 (public rss)")

    print("Cosechando Reddit por RSS (sin credenciales)...")
    posts = reader.trending(TARGET_SUBREDDITS, max_subs=2, per_sub=8)
    added = store.harvest(posts, now=_NOW)
    print(f"Leidos {len(posts)} posts | nuevos guardados: {added}")
    print(f"Cola total: {store.count()} | pendientes: {store.count('new')} | usadas: {store.count('used')}")
    print("\nOportunidades pendientes (para adaptar luego):")
    for oppo in store.pending(limit=8):
        print(f"  [{oppo.subreddit}] {oppo.theme_hint[:80]}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
