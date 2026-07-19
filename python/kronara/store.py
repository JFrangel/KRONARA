from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    node: str
    state: dict[str, Any]


@dataclass(frozen=True)
class WorkflowEvent:
    run_id: str
    kind: str
    payload: dict[str, Any]


class KronaraStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS workflow_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                run_id TEXT PRIMARY KEY,
                node TEXT NOT NULL,
                state_json TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def _db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("store is not initialized")
        return self.connection

    def append_event(self, run_id: str, kind: str, payload: dict[str, Any]) -> None:
        self._db().execute(
            "INSERT INTO workflow_events(run_id, kind, payload_json) VALUES (?, ?, ?)",
            (run_id, kind, json.dumps(payload, sort_keys=True)),
        )
        self._db().commit()

    def save_checkpoint(self, run_id: str, node: str, state: dict[str, Any]) -> None:
        self._db().execute(
            """
            INSERT INTO checkpoints(run_id, node, state_json) VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET node=excluded.node, state_json=excluded.state_json
            """,
            (run_id, node, json.dumps(state, sort_keys=True)),
        )
        self._db().commit()

    def load_checkpoint(self, run_id: str) -> Checkpoint:
        row = self._db().execute(
            "SELECT node, state_json FROM checkpoints WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return Checkpoint(run_id, row[0], json.loads(row[1]))

    def replay(self, run_id: str) -> list[WorkflowEvent]:
        rows = self._db().execute(
            "SELECT kind, payload_json FROM workflow_events WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        )
        return [WorkflowEvent(run_id, kind, json.loads(payload)) for kind, payload in rows]

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

