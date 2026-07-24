"""Regression: the store must be usable from a worker thread.

``content.run`` (fire-and-poll) runs the whole pipeline in a background
``threading.Thread`` and writes to the store as it advances
(save_tool_trace / append_event). The SQLite connection is created on the
MAIN thread at ``initialize()``; without ``check_same_thread=False`` the
worker thread raised ``sqlite3.ProgrammingError: SQLite objects created in
a thread can only be used in that same thread``, which failed every episode
created from the UI at ~8% (the first tool trace of the Reddit research).
"""

from __future__ import annotations

import threading

from kronara.store import KronaraStore


def test_write_from_worker_thread(tmp_path):
    store = KronaraStore(tmp_path / "kronara.db")
    store.initialize()  # connection created on the MAIN thread
    try:
        errors: list[Exception] = []

        def worker() -> None:
            try:
                store.append_event("content:demo", "content.started", {"ok": True})
            except Exception as exc:  # noqa: BLE001 - capture for the assertion
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        assert errors == [], f"worker-thread write raised: {errors!r}"
        # The row written from the worker thread is readable from the main thread.
        assert any(e.kind == "content.started" for e in store.replay("content:demo"))
    finally:
        store.close()
