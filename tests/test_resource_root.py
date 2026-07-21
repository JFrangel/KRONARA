"""Regression coverage for the bug found by directly probing the frozen
sidecar binary: programs.list failed looking for
"%TEMP%/config/programs/programs.v1.json" because several modules computed
their own Path(__file__).resolve().parents[2] instead of accounting for
PyInstaller's frozen extraction directory. Every other test in this suite
runs unfrozen (sys._MEIPASS unset), which is exactly why the bug shipped
undetected -- these tests are the only ones that simulate frozen mode."""

from __future__ import annotations

import sys
from pathlib import Path

from kronara.resource_root import resource_root


def test_resource_root_is_the_repo_root_when_not_frozen():
    root = resource_root()

    assert (root / "config").is_dir()
    assert (root / "python" / "kronara").is_dir()


def test_resource_root_uses_the_pyinstaller_extraction_dir_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resource_root() == tmp_path


def test_programs_default_registry_path_stays_inside_the_frozen_bundle(monkeypatch, tmp_path):
    """The exact failure observed against the real binary: climbing
    Path(__file__).resolve().parents[2] from inside a frozen bundle escapes
    it into bare %TEMP%, which has no config/ subfolder at all."""
    from kronara.programs import default_registry_path

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    path = default_registry_path()

    assert Path(tmp_path) in path.parents
    assert path == tmp_path / "config" / "programs" / "programs.v1.json"


def test_visual_style_default_registry_path_stays_inside_the_frozen_bundle(monkeypatch, tmp_path):
    from kronara.visual_style import default_registry_path

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert default_registry_path() == tmp_path / "config" / "programs" / "visual_style.v1.json"


def test_reddit_source_map_default_dir_stays_inside_the_frozen_bundle(monkeypatch, tmp_path):
    from kronara.reddit_source_map import _default_sources_dir

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert _default_sources_dir() == tmp_path / "knowledge" / "reddit-sources"
