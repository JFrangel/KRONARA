"""Harvest story opportunities from Reddit RSS (no credentials) and save them.

One run reads several target subreddits via public RSS (no app, no login, no
password), de-duplicates against what is already stored, and persists the new
posts so later iterations can adapt them without re-hitting Reddit. Reddit
rate-limits these feeds, so it reads a couple of subs per run with backoff.

Target subreddits come from `knowledge/reddit-sources/nodo-*.md` (the RAG
source-node docs), not a hardcoded list — editing those files changes what
gets harvested. Pass a program's node filename (e.g. "viernes-paranormal") to
harvest only that program's sources; omit it to harvest across all nodes.

Usage: python scripts/harvest_reddit.py [nodo-name]
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from kronara.opportunities import OpportunityStore  # noqa: E402
from kronara.reddit_rss import RedditRssReader  # noqa: E402
from kronara.reddit_source_map import load_source_map  # noqa: E402

# Deterministic-ish timestamp source without a wall clock in the demo.
_NOW = 1_800_000_000


def target_subreddits(node_filter: str | None = None) -> dict[str, str]:
    """{subreddit: sensitivity}, optionally restricted to one node file."""
    source_map = load_source_map()
    return {
        entry.subreddit: entry.sensitivity
        for entry in source_map.values()
        if node_filter is None or node_filter in entry.node_file
    }


def main() -> int:
    node_filter = sys.argv[1] if len(sys.argv) > 1 else None
    subreddits = target_subreddits(node_filter)
    if not subreddits:
        print(f"Sin subreddits para el filtro {node_filter!r} (revisa knowledge/reddit-sources/)")
        return 1

    db = Path(__file__).resolve().parents[1] / ".kronara" / "opportunities.db"
    store = OpportunityStore(db).initialize()
    reader = RedditRssReader(user_agent="windows:kronara45:v0.6 (public rss)")

    print(f"Cosechando Reddit por RSS (sin credenciales) — {len(subreddits)} subreddits...")
    posts = reader.trending(list(subreddits), max_subs=2, per_sub=8)
    # Attach each post's sensitivity from the node it belongs to.
    posts = [replace(post, sensitivity=subreddits.get(post.subreddit, "entertainment")) for post in posts]
    added = store.harvest(posts, now=_NOW)
    print(f"Leidos {len(posts)} posts | nuevos guardados: {added}")
    print(f"Cola total: {store.count()} | pendientes: {store.count('new')} | usadas: {store.count('used')}")
    print("\nOportunidades pendientes (para adaptar luego):")
    for oppo in store.pending(limit=8):
        flag = " [serio]" if oppo.sensitivity == "real_experience_serious" else ""
        print(f"  [{oppo.subreddit}]{flag} {oppo.theme_hint[:75]}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
