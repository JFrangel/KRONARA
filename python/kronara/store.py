from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from kronara.operations_contracts import MemoryRecord, ToolTraceEvent


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
        if self.connection is None:
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
            CREATE TABLE IF NOT EXISTS improvement_decisions (
                version_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS error_memories (
                error_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS learning_hypotheses (
                hypothesis_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tool_trace_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tool_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tool_trace_run_sequence
                ON tool_trace_events(run_id, sequence);
            CREATE TABLE IF NOT EXISTS memory_records (
                record_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                scope TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memory_scope_kind
                ON memory_records(scope, kind);
            CREATE TABLE IF NOT EXISTS conversation_turns (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_turns
                ON conversation_turns(conversation_id, sequence);
            CREATE TABLE IF NOT EXISTS embedding_index_manifests (
                index_id TEXT PRIMARY KEY,
                model_alias TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reddit_query_receipts (
                receipt_id TEXT PRIMARY KEY,
                query_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owned_story_reuse_decisions (
                story_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS owned_story_artifacts (
                story_id TEXT PRIMARY KEY,
                artifact_uri TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS performance_metric_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                content_id TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_performance_metrics_platform
                ON performance_metric_snapshots(platform, content_id);
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

    def save_improvement_decision(
        self,
        version_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        self._db().execute(
            """
            INSERT INTO improvement_decisions(version_id, status, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(version_id) DO UPDATE SET
                status=excluded.status,
                payload_json=excluded.payload_json
            """,
            (version_id, status, json.dumps(payload, sort_keys=True)),
        )
        self._db().commit()

    def load_improvement_decision(self, version_id: str) -> dict[str, Any]:
        row = self._db().execute(
            "SELECT status, payload_json FROM improvement_decisions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise KeyError(version_id)
        payload = json.loads(row[1])
        payload["status"] = row[0]
        return payload

    def save_error_memory(self, error_id: str, payload: dict[str, Any]) -> None:
        self._db().execute(
            """
            INSERT INTO error_memories(error_id, payload_json) VALUES (?, ?)
            ON CONFLICT(error_id) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (error_id, json.dumps(payload, sort_keys=True)),
        )
        self._db().commit()

    def load_error_memory(self, error_id: str) -> dict[str, Any]:
        row = self._db().execute(
            "SELECT payload_json FROM error_memories WHERE error_id = ?", (error_id,)
        ).fetchone()
        if row is None:
            raise KeyError(error_id)
        return json.loads(row[0])

    def save_learning_hypothesis(
        self, hypothesis_id: str, payload: dict[str, Any]
    ) -> None:
        self._db().execute(
            """
            INSERT INTO learning_hypotheses(hypothesis_id, payload_json) VALUES (?, ?)
            ON CONFLICT(hypothesis_id) DO UPDATE SET payload_json=excluded.payload_json
            """,
            (hypothesis_id, json.dumps(payload, sort_keys=True)),
        )
        self._db().commit()

    def list_learning_hypotheses(self) -> list[dict[str, Any]]:
        rows = self._db().execute(
            "SELECT payload_json FROM learning_hypotheses ORDER BY hypothesis_id"
        )
        return [json.loads(row[0]) for row in rows]

    def save_tool_trace(self, event: ToolTraceEvent) -> None:
        payload = json.dumps(asdict(event), sort_keys=True, default=self._json_default)
        self._db().execute(
            """
            INSERT INTO tool_trace_events(
                event_id, run_id, agent_id, tool_id, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event.event_id, event.run_id, event.agent_id, event.tool_id, event.status, payload),
        )
        self._db().commit()

    def list_tool_traces(self, run_id: str) -> list[ToolTraceEvent]:
        rows = self._db().execute(
            "SELECT payload_json FROM tool_trace_events WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        )
        events: list[ToolTraceEvent] = []
        for (payload_json,) in rows:
            payload = json.loads(payload_json)
            payload["started_at"] = datetime.fromisoformat(payload["started_at"])
            if payload.get("finished_at") is not None:
                payload["finished_at"] = datetime.fromisoformat(payload["finished_at"])
            for key in ("evidence_refs", "artifact_refs", "policy_findings"):
                payload[key] = tuple(payload.get(key, ()))
            events.append(ToolTraceEvent(**payload))
        return events

    def save_memory(self, record: MemoryRecord) -> None:
        payload = json.dumps(asdict(record), sort_keys=True)
        self._db().execute(
            """
            INSERT INTO memory_records(record_id, kind, scope, status, payload_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                kind=excluded.kind,
                scope=excluded.scope,
                status=excluded.status,
                payload_json=excluded.payload_json
            """,
            (record.record_id, record.kind, record.scope, record.status, payload),
        )
        self._db().commit()

    def search_memory(self, scope: str, kind: str | None = None) -> list[MemoryRecord]:
        if kind is None:
            rows = self._db().execute(
                "SELECT payload_json FROM memory_records WHERE scope = ? ORDER BY record_id",
                (scope,),
            )
        else:
            rows = self._db().execute(
                """
                SELECT payload_json FROM memory_records
                WHERE scope = ? AND kind = ? ORDER BY record_id
                """,
                (scope, kind),
            )
        records: list[MemoryRecord] = []
        for (payload_json,) in rows:
            payload = json.loads(payload_json)
            payload["evidence_refs"] = tuple(payload.get("evidence_refs", ()))
            records.append(MemoryRecord(**payload))
        return records

    def save_conversation_turn(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        created_at: datetime,
    ) -> None:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("unsupported conversation role")
        self._db().execute(
            """
            INSERT INTO conversation_turns(conversation_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, role, content, created_at.isoformat()),
        )
        self._db().commit()

    def list_conversation_turns(self, conversation_id: str) -> list[dict[str, str]]:
        rows = self._db().execute(
            """
            SELECT role, content, created_at FROM conversation_turns
            WHERE conversation_id = ? ORDER BY sequence
            """,
            (conversation_id,),
        )
        return [
            {"role": role, "content": content, "created_at": created_at}
            for role, content, created_at in rows
        ]

    def save_story_reuse_decision(
        self, story_id: str, status: str, payload: dict[str, Any]
    ) -> None:
        self._db().execute(
            """
            INSERT INTO owned_story_reuse_decisions(story_id, status, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(story_id) DO UPDATE SET
                status=excluded.status,
                payload_json=excluded.payload_json
            """,
            (story_id, status, json.dumps(payload, sort_keys=True)),
        )
        self._db().commit()

    def load_story_reuse_decision(self, story_id: str) -> dict[str, Any]:
        row = self._db().execute(
            """
            SELECT status, payload_json FROM owned_story_reuse_decisions
            WHERE story_id = ?
            """,
            (story_id,),
        ).fetchone()
        if row is None:
            raise KeyError(story_id)
        payload = json.loads(row[1])
        payload["status"] = row[0]
        return payload

    def save_owned_story_artifact(
        self,
        *,
        story_id: str,
        artifact_uri: str,
        path: str,
        sha256: str,
        metadata: dict[str, Any],
    ) -> None:
        if not all((story_id, artifact_uri, path, sha256)):
            raise ValueError("owned story artifact identity is required")
        self._db().execute(
            """
            INSERT INTO owned_story_artifacts(
                story_id, artifact_uri, path, sha256, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(story_id) DO UPDATE SET
                artifact_uri=excluded.artifact_uri,
                path=excluded.path,
                sha256=excluded.sha256,
                metadata_json=excluded.metadata_json
            """,
            (
                story_id,
                artifact_uri,
                path,
                sha256,
                json.dumps(metadata, sort_keys=True, ensure_ascii=False),
            ),
        )
        self._db().commit()

    def load_owned_story_artifact(self, story_id: str) -> dict[str, Any]:
        row = self._db().execute(
            """
            SELECT artifact_uri, path, sha256, metadata_json
            FROM owned_story_artifacts WHERE story_id = ?
            """,
            (story_id,),
        ).fetchone()
        if row is None:
            raise KeyError(story_id)
        return {
            "story_id": story_id,
            "artifact_uri": row[0],
            "path": row[1],
            "sha256": row[2],
            "metadata": json.loads(row[3]),
        }

    def save_metric_snapshot(self, payload: dict[str, Any]) -> None:
        snapshot_id = str(payload.get("snapshot_id", ""))
        platform = str(payload.get("platform", ""))
        content_id = str(payload.get("content_id", ""))
        if not all((snapshot_id, platform, content_id)):
            raise ValueError("metric snapshot identity is required")
        self._db().execute(
            """
            INSERT INTO performance_metric_snapshots(
                snapshot_id, platform, content_id, payload_json
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                platform=excluded.platform,
                content_id=excluded.content_id,
                payload_json=excluded.payload_json
            """,
            (
                snapshot_id,
                platform,
                content_id,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        )
        self._db().commit()

    def list_metric_snapshots(self, platform: str) -> list[dict[str, Any]]:
        rows = self._db().execute(
            """
            SELECT payload_json FROM performance_metric_snapshots
            WHERE platform = ? ORDER BY snapshot_id
            """,
            (platform,),
        )
        return [json.loads(row[0]) for row in rows]

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"unsupported JSON value: {type(value).__name__}")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
