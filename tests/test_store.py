import sqlite3
from pathlib import Path

from kronara.store import KronaraStore


def test_store_persists_checkpoint_and_replays_events(tmp_path: Path):
    database = tmp_path / "kronara.db"
    store = KronaraStore(database)
    store.initialize()
    store.append_event("run_1", "workflow.started", {"mode": "full_auto"})
    store.save_checkpoint("run_1", "opportunity_intelligence", {"topic": "mystery"})
    store.close()

    reopened = KronaraStore(database)
    reopened.initialize()

    assert reopened.load_checkpoint("run_1").state == {"topic": "mystery"}
    assert [event.kind for event in reopened.replay("run_1")] == ["workflow.started"]


def test_initialize_migrates_a_pre_existing_db_missing_created_at_and_program_id(tmp_path: Path):
    """Regression test: a real local .kronara/runtime/kronara.db predating
    created_at/program_id broke sidecar startup (CREATE TABLE IF NOT EXISTS
    is a no-op against an existing table, so the columns and the index on
    them must be added via an explicit, idempotent migration)."""
    database = tmp_path / "kronara.db"
    old_connection = sqlite3.connect(database)
    old_connection.executescript(
        """
        CREATE TABLE owned_story_artifacts (
            story_id TEXT PRIMARY KEY,
            artifact_uri TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
        """
    )
    old_connection.execute(
        "INSERT INTO owned_story_artifacts VALUES ('ep_old', 'kronara://sha256/x', '/x', 'x', '{}')"
    )
    old_connection.commit()
    old_connection.close()

    store = KronaraStore(database)
    store.initialize()  # must not raise "no such column: created_at"

    loaded = store.load_owned_story_artifact("ep_old")
    assert loaded["created_at"] == 0
    assert loaded["program_id"] == ""
    assert store.list_owned_story_artifacts() == [loaded]
    store.close()


def _seed_artifact(store, story_id, *, created_at, program_id="viernes-paranormal", title=None):
    store.save_owned_story_artifact(
        story_id=story_id,
        artifact_uri=f"kronara://sha256/{story_id}",
        path=f"/artifacts/{story_id}",
        sha256=story_id,
        created_at=created_at,
        program_id=program_id,
        metadata={"title": title or story_id, "duration_seconds": 95.0},
    )


def test_load_owned_story_artifact_returns_created_at_and_program_id(tmp_path: Path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    _seed_artifact(store, "ep_1", created_at=100, program_id="viernes-paranormal")

    loaded = store.load_owned_story_artifact("ep_1")

    assert loaded["created_at"] == 100
    assert loaded["program_id"] == "viernes-paranormal"
    store.close()


def test_list_owned_story_artifacts_orders_most_recent_first(tmp_path: Path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    _seed_artifact(store, "ep_old", created_at=100)
    _seed_artifact(store, "ep_new", created_at=300)
    _seed_artifact(store, "ep_mid", created_at=200)

    episodes = store.list_owned_story_artifacts()

    assert [item["story_id"] for item in episodes] == ["ep_new", "ep_mid", "ep_old"]
    store.close()


def test_list_owned_story_artifacts_respects_limit(tmp_path: Path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    for i in range(5):
        _seed_artifact(store, f"ep_{i}", created_at=i)

    assert len(store.list_owned_story_artifacts(limit=2)) == 2
    store.close()


def test_list_owned_story_artifacts_rejects_out_of_range_limit(tmp_path: Path):
    import pytest

    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()
    with pytest.raises(ValueError):
        store.list_owned_story_artifacts(limit=0)
    store.close()

