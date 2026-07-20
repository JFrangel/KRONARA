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


def _parse_node_table(path: Path) -> list[tuple[str, str]]:
    """One (subreddit_name, sensitivity) pair per data row in a `nodo-*.md`
    table, in file order, deduplicated only within this single file. Shared
    by load_source_map() (which does its own cross-file dedup on top) and
    subreddits_for_program() (which deliberately does NOT cross-file dedup --
    see its docstring)."""
    seen: set[str] = set()
    rows: list[tuple[str, str]] = []
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
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            rows.append((name, sensitivity))
    return rows


def load_source_map(sources_dir: Path | str | None = None) -> dict[str, SourceEntry]:
    """Parse every `nodo-*.md` table into {subreddit_lower: SourceEntry}.

    A subreddit appearing in more than one node keeps the first (most specific)
    entry encountered; files are read in sorted order for determinism. This
    cross-file dedup is right for its purpose -- a global "is X ever
    sensitive" answer only needs one entry per subreddit -- but it is WRONG
    for "which subreddits feed program Y" (see subreddits_for_program, which
    deliberately bypasses this and reads one file directly instead).
    """
    directory = Path(sources_dir) if sources_dir is not None else _default_sources_dir()
    entries: dict[str, SourceEntry] = {}
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("nodo-*.md")):
        for name, sensitivity in _parse_node_table(path):
            key = name.casefold()
            if key not in entries:
                entries[key] = SourceEntry(subreddit=name, node_file=path.name, sensitivity=sensitivity)
    return entries


def sensitivity_for(subreddit: str, source_map: dict[str, SourceEntry]) -> str:
    entry = source_map.get(subreddit.casefold())
    return entry.sensitivity if entry is not None else DEFAULT_SENSITIVITY


def subreddits_for_program(program_id: str, sources_dir: Path | str | None = None) -> tuple[str, ...]:
    """Every subreddit listed in `nodo-<program_id>.md`, in the file's own
    order -- F0's node filenames match visual_style.v1.json's program_id
    slugs exactly, so this is the autonomous scheduler's link from "which
    program is due" to "which subreddits to investigate for it."

    Deliberately reads the one target file directly rather than filtering
    load_source_map()'s cross-file-deduplicated result: a subreddit like
    r/nosleep legitimately feeds more than one program (short scary stories
    for Viernes Paranormal, longer ones for Historias de Medianoche), and
    load_source_map()'s "keep only the first file encountered" rule would
    silently drop it from every program except whichever sorts first --
    which would have made this program's harvester quietly search a
    shorter, wrong subreddit list than the one actually authored for it.

    A missing/mis-slugged node file returns an empty tuple rather than
    raising -- degrade to "nothing to harvest," don't crash the scheduler
    tick over one bad program entry.
    """
    directory = Path(sources_dir) if sources_dir is not None else _default_sources_dir()
    path = directory / f"nodo-{program_id}.md"
    if not path.is_file():
        return ()
    return tuple(name for name, _sensitivity in _parse_node_table(path))
