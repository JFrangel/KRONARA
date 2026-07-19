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

