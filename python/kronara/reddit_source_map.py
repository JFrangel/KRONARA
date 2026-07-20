"""Parses `knowledge/reddit-sources/*.md` into a subreddit -> sensitivity map.

The nodo files ARE the source of truth for which subreddits feed which program
and how sensitive their content is (see `knowledge/reddit-sources/INDICE.md`).
This module reads those markdown tables at runtime instead of duplicating the
list in Python, so editing a `.md` file is enough to change harvesting policy.

Table row shape (one per subreddit): `| name | description | sensitivity |`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_VALID_SENSITIVITY = {"entertainment", "real_experience_serious"}
_SEPARATOR_ROW = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$")

DEFAULT_SENSITIVITY = "entertainment"


def _split_row(line: str) -> list[str] | None:
    """Split a `| a | b | c |` markdown row into cells, tolerant of any cell
    content (parentheses, quotes, em dashes) since it splits on `|`, not on a
    character class for the cell contents."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped[1:-1].split("|")]
    return cells if len(cells) >= 2 else None


@dataclass(frozen=True)
class SourceEntry:
    subreddit: str
    node_file: str
    sensitivity: str


def _default_sources_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "knowledge" / "reddit-sources"


def load_source_map(sources_dir: Path | str | None = None) -> dict[str, SourceEntry]:
    """Parse every `nodo-*.md` table into {subreddit_lower: SourceEntry}.

    A subreddit appearing in more than one node keeps the first (most specific)
    entry encountered; files are read in sorted order for determinism.
    """
    directory = Path(sources_dir) if sources_dir is not None else _default_sources_dir()
    entries: dict[str, SourceEntry] = {}
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("nodo-*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if _SEPARATOR_ROW.match(line.strip()):
                continue
            cells = _split_row(line)
            if cells is None or len(cells) < 3:
                continue
            raw_name, sensitivity = cells[0], cells[-1]
            if sensitivity not in _VALID_SENSITIVITY:
                continue
            # Rows like "AmItheAsshole (flair Serious)" / "JustNoFamily / JustNoMIL"
            # -> take each slash-separated, parenthetical-stripped subreddit name.
            for name in raw_name.split("/"):
                name = re.sub(r"\(.*?\)", "", name).strip()
                if not name:
                    continue
                key = name.casefold()
                if key not in entries:
                    entries[key] = SourceEntry(
                        subreddit=name, node_file=path.name, sensitivity=sensitivity
                    )
    return entries


def sensitivity_for(subreddit: str, source_map: dict[str, SourceEntry]) -> str:
    entry = source_map.get(subreddit.casefold())
    return entry.sensitivity if entry is not None else DEFAULT_SENSITIVITY
