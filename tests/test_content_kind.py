from pathlib import Path

import pytest

from kronara.content_pipeline import ProductionContentPipeline
from kronara.model_registry_v2 import ModelCapabilityRegistryV2

ROOT = Path(__file__).resolve().parents[1]


class _Store:
    def __init__(self):
        self.events = []

    def append_event(self, run_id, kind, payload):
        self.events.append((run_id, kind, payload))


def _pipeline(tmp_path):
    return ProductionContentPipeline(
        authority=object(),
        store=_Store(),
        rag=object(),
        model_registry=ModelCapabilityRegistryV2.load(ROOT / "config" / "models" / "registry.v2.json"),
        artifact_root=tmp_path / "artifacts",
    )


@pytest.mark.parametrize("kind", ["reflection", "scripture", "quote"])
def test_non_narrative_kinds_branch_to_shortform_without_reddit(tmp_path, kind):
    pipeline = _pipeline(tmp_path)
    # A fresh authority object() would explode the moment the Reddit path touched
    # it -- so reaching a completed brief here proves the short-form branch never
    # went near Reddit/the authority.
    state = pipeline._stage_estratega({"params": {"content_kind": kind, "story_id": "owned-x", "theme": "la calma"}})
    brief = state["brief"]
    assert brief.content_kind == kind
    assert brief.theme == "la calma"
    assert brief.rights_mode == "owned_original"
    assert brief.source_uri.startswith("kronara://artifacts/")
    assert brief.source_case == ""  # no reconstruction in short-form modes
    assert brief.target_duration_seconds == 45
    # Reddit-specific state is honestly empty.
    assert state["selected_signal"] is None
    assert state["rejected_signals"] == {}
    assert state["receipt"] == {}
    # Evidence is the corpus/mode itself, never a fabricated Reddit source.
    assert state["evidence"] == [f"kronara://corpus/{kind}"]
    # The mode is logged for the live view / traceability.
    assert any(k == "agent.log" and p.get("action") == "content.mode" for _r, k, p in pipeline.store.events)


def test_shortform_uses_defaults_when_no_theme_given(tmp_path):
    pipeline = _pipeline(tmp_path)
    state = pipeline._stage_estratega({"params": {"content_kind": "quote", "story_id": "owned-y"}})
    assert state["brief"].content_kind == "quote"
    assert state["brief"].theme  # a default aphorism theme was supplied
    assert state["brief"].premise
