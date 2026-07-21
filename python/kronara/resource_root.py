"""The single source of truth for finding bundled data (config/, knowledge/,
benchmarks/) from any module -- in dev, the repo root; in a frozen
PyInstaller build, the extraction directory --add-data unpacked those
folders into.

Before this module existed, sidecar.py's own _resource_root() got this
right, but programs.py, visual_style.py, reddit_source_map.py, and
narrative_workflow.py each independently wrote plain
``Path(__file__).resolve().parents[2]`` for the same purpose. That works in
dev (this file's parents[2] is the repo root either way) but silently
breaks in the frozen .exe: a frozen __file__ resolves inside the
_MEIxxxxxx extraction folder, and climbing two parents up from
``_MEIxxxxxx/kronara/programs.py`` escapes the bundle entirely and lands on
bare %TEMP%, which has no config/ subfolder -- confirmed by directly
probing the packaged sidecar binary, where programs.list failed looking
for ``%TEMP%/config/programs/programs.v1.json``. Every module that needs
the bundled data root must import resource_root() from here instead of
re-deriving it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]
