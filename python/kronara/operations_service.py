from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from kronara.embedding_registry import EmbeddingRegistry
from kronara.observable_tools import ObservableToolRegistry
from kronara.operations_chat import OperationsChatAgent
from kronara.operations_contracts import OperationsChatRequest
from kronara.prompt_stack import PersonaProfile, PromptStackCompiler
from kronara.rag_v2 import DeterministicHashEmbedder, IngestDocument
from kronara.rag_v3 import RAGV3Index, RetrievalQueryV3
from kronara.store import KronaraStore
from kronara.story_engine import (
    DeterministicIndependentCritic,
    DeterministicStoryProvider,
    StoryBrief,
    StoryEngine,
)
from kronara.tools import ToolRegistry, ToolSpec


class LocalOperationsResponder:
    """Offline operational summary used when no routed model is configured."""

    family = "local-operations-summary"

    def answer(self, _: str) -> str:
        return (
            "Kronara está operativa en modo local y conserva evidencia de sus "
            "herramientas. La publicación real permanece bajo autoridad de Rust; "
            "cualquier cambio administrativo se entrega como propuesta para aprobación."
        )


class OperationsService:
    """Bounded RPC facade for chat, retrieval, traces and recoverable story tests."""

    def __init__(self, data_dir: Path, *, resource_root: Path | None = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.resource_root = resource_root or Path(__file__).resolve().parents[2]
        self.database_path = self.data_dir / "kronara.db"
        self.store = KronaraStore(self.database_path)
        self.store.initialize()
        self._states: dict[str, dict[str, Any]] = {}
        self._cancellations: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._paused = False
        self._rag = self._build_rag()
        self._chat = self._build_chat()

    def methods(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        return {
            "operations.chat": self.operations_chat,
            "operations.context": self.operations_context,
            "tools.timeline": self.tool_timeline,
            "memory.search": self.memory_search,
            "rag.retrieve_v3": self.rag_retrieve,
            "story.test": self.story_test,
            "run.cancel": self.cancel,
            "run.progress": self.progress,
            "operations.control_snapshot": self.control_snapshot,
        }

    def operations_chat(self, params: dict[str, Any]) -> dict[str, Any]:
        request = OperationsChatRequest(
            schema_version=int(params.get("schema_version", 1)),
            request_id=str(params["request_id"]),
            conversation_id=str(params["conversation_id"]),
            message=str(params["message"]),
            minimum_context_coverage=float(params.get("minimum_context_coverage", 0.7)),
        )
        return self._json(asdict(self._chat.answer(request)))

    def operations_context(self, _: dict[str, Any]) -> dict[str, Any]:
        status = self._status_snapshot()
        return {
            "schema_version": 1,
            "run_ids": status["run_ids"],
            "workflow_snapshot": status["workflow_snapshot"],
            "evidence_refs": status["evidence"],
            "citations": status["citations"],
            "provider_status": status["provider_status"],
            "budget_status": status["budget_status"],
            "coverage": 1.0,
            "missing_topics": [],
        }

    def tool_timeline(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = str(params.get("run_id") or "")
        if not run_id:
            with self._lock:
                run_ids = list(self._states)[-5:]
            events = [
                event
                for candidate in run_ids
                for event in self.store.list_tool_traces(candidate)
                if event.status != "started"
            ]
        else:
            events = [
                event
                for event in self.store.list_tool_traces(run_id)
                if event.status != "started"
            ]
        return {
            "schema_version": 1,
            "run_id": run_id or None,
            "count": len(events),
            "events": [self._json(asdict(event)) for event in events[-200:]],
        }

    def memory_search(self, params: dict[str, Any]) -> dict[str, Any]:
        scope = str(params["scope"])
        kind = str(params["kind"]) if params.get("kind") is not None else None
        limit = int(params.get("limit", 20))
        if not 1 <= limit <= 50:
            raise ValueError("memory search limit must be between one and fifty")
        records = self.store.search_memory(scope, kind)[:limit]
        return {
            "schema_version": 1,
            "scope": scope,
            "records": [self._json(asdict(record)) for record in records],
        }

    def rag_retrieve(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 8))
        packet = self._rag.retrieve(
            RetrievalQueryV3(
                text=str(params["query"]),
                now=int(params.get("now", int(datetime.now(UTC).timestamp()))),
                language=str(params.get("language", "es")),
                scope=str(params.get("scope", "narrative")),
                allowed_rights=("owned_original", "promoted_learning"),
                limit=limit,
                max_per_document=min(2, limit),
            )
        )
        payload = self._json(asdict(packet))
        payload["degradations"] = list(
            dict.fromkeys((*payload["degradations"], "development_embedding_only"))
        )
        return payload

    def story_test(self, params: dict[str, Any]) -> dict[str, Any]:
        brief = self._story_brief(params)
        run_id = f"story:{brief.story_id}"
        if bool(params.get("wait", False)):
            with self._lock:
                self._states[run_id] = self._run_state(run_id, "running", 10, "guardian_input")
            result = self._execute_story(brief, self.store)
            return result
        cancellation = threading.Event()
        with self._lock:
            existing = self._states.get(run_id)
            if existing and existing["status"] in {"queued", "running"}:
                return dict(existing)
            self._cancellations[run_id] = cancellation
            self._states[run_id] = self._run_state(run_id, "queued", 0, "queued")
        thread = threading.Thread(
            target=self._story_worker,
            args=(brief, cancellation),
            name=f"kronara-{brief.story_id}",
            daemon=True,
        )
        self._threads[run_id] = thread
        thread.start()
        return dict(self._states[run_id])

    def progress(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = str(params["run_id"])
        with self._lock:
            current = dict(
                self._states.get(run_id, self._run_state(run_id, "unknown", 0, "not_found"))
            )
        if current["status"] == "running":
            try:
                checkpoint = self.store.load_checkpoint(run_id)
                percentages = {
                    "guardian_input": 10,
                    "concept_selection": 25,
                    "causal_blueprint": 40,
                    "script_assembly": 55,
                    "originality": 70,
                    "independent_critique": 85,
                    "guardian": 100,
                }
                current["node"] = checkpoint.node
                current["progress_percent"] = percentages.get(
                    checkpoint.node, current["progress_percent"]
                )
                with self._lock:
                    self._states[run_id] = dict(current)
            except KeyError:
                pass
        return current

    def control_snapshot(self, params: dict[str, Any]) -> dict[str, Any]:
        paused = params.get("paused")
        if not isinstance(paused, bool):
            raise ValueError("paused must be a boolean")
        with self._lock:
            self._paused = paused
        return {"schema_version": 1, "paused": paused}

    def cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = str(params["run_id"])
        with self._lock:
            current = self._states.get(run_id)
            if current is None:
                cancelled = self._run_state(run_id, "cancelled", 100, "cancelled")
                self._states[run_id] = cancelled
                return dict(cancelled)
            if current["status"] in {"cancelled", "completed", "blocked", "failed"}:
                return dict(current)
            cancellation = self._cancellations.setdefault(run_id, threading.Event())
            cancellation.set()
            current = self._run_state(
                run_id,
                "cancellation_requested",
                int(current["progress_percent"]),
                str(current["node"]),
            )
            self._states[run_id] = current
            return dict(current)

    def close(self) -> None:
        for event in self._cancellations.values():
            event.set()
        for thread in self._threads.values():
            thread.join(timeout=2)
        self._rag.close()
        self.store.close()

    def _build_chat(self) -> OperationsChatAgent:
        persona_payload = json.loads(
            (self.resource_root / "config" / "personas" / "kronara.v1.json").read_text(
                encoding="utf-8"
            )
        )
        registry = ToolRegistry(
            (
                ToolSpec("operations.status", lambda _: self._status_snapshot()),
                ToolSpec("tools.timeline", self._chat_timeline),
                ToolSpec("evidence.read", lambda _: {"count": 1, "evidence": ["ev_runtime"]}),
                ToolSpec("metrics.read", lambda _: {"count": 0, "evidence": []}),
                ToolSpec("performance.diagnose", lambda _: {"count": 0, "evidence": []}),
                ToolSpec("memory.search", lambda _: {"count": 0, "evidence": []}),
            )
        )
        tools = ObservableToolRegistry(
            registry,
            store=self.store,
            summarizers={
                "operations.status": lambda value: str(value["summary"]),
                "tools.timeline": lambda value: str(value["summary"]),
            },
        )
        return OperationsChatAgent(
            tools=tools,
            store=self.store,
            prompt_compiler=PromptStackCompiler(),
            persona=PersonaProfile.from_dict(persona_payload),
            responder=LocalOperationsResponder(),
        )

    def _build_rag(self) -> RAGV3Index:
        registry = EmbeddingRegistry.load(
            self.resource_root / "config" / "models" / "embeddings.v1.json"
        )
        descriptor = registry.get("deterministic_dev")
        index = RAGV3Index(
            self.data_dir / "knowledge.db",
            descriptor,
            DeterministicHashEmbedder(descriptor.dimensions),
        )
        index.upsert(
            IngestDocument(
                document_id="kronara_runtime_policy_v1",
                title="Política operativa de Kronara",
                content=(
                    "# Derechos y autoridad\nKronara solo reutiliza historias propias o con licencia "
                    "verificable. Rust conserva la autoridad sobre secretos, red, archivos y "
                    "publicación. Python razona mediante herramientas permitidas.\n\n"
                    "# Aprendizaje\nLos resultados crean hipótesis reversibles. Una historia propia "
                    "solo se promueve con muestra suficiente, calidad aprobada y evidencia."
                ),
                rights_mode="owned_original",
                language="es",
                scope="narrative",
                valid_from=0,
                valid_until=None,
                confidence=1.0,
                version=1,
            )
        )
        return index

    def _status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = {
                run_id: state["status"]
                for run_id, state in self._states.items()
                if state["status"] not in {"completed", "blocked", "failed", "cancelled"}
            }
            run_ids = list(self._states)[-10:] or ["runtime:local"]
        return {
            "summary": "Plano cognitivo local disponible; efectos externos gobernados por Rust.",
            "run_ids": run_ids,
            "workflow_snapshot": {
                "mode": "full_auto",
                "paused": self._paused,
                "active_runs": active,
                "publication_authority": "rust_only",
            },
            "evidence": ["ev_runtime_policy"],
            "citations": ["kronara://knowledge/kronara_runtime_policy_v1"],
            "memory_record_ids": [],
            "provider_status": {
                "operations_summary": "healthy_local",
                "production_models": "configured_by_rust",
            },
            "budget_status": {"remaining_usd": 5.0, "maximum_usd": 5.0},
        }

    def _chat_timeline(self, _: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            count = len(self._states)
        return {
            "summary": f"{count} ejecuciones registradas; trazas detalladas disponibles por run_id.",
            "count": count,
            "evidence": ["ev_runtime_policy"],
        }

    def _story_brief(self, params: dict[str, Any]) -> StoryBrief:
        if params.get("brief") is not None:
            return StoryBrief.from_dict(dict(params["brief"]))
        payload = json.loads(
            (self.resource_root / "benchmarks" / "golden" / "story-runtime.v2.json").read_text(
                encoding="utf-8"
            )
        )
        brief = dict(payload["brief"])
        if params.get("story_id") is not None:
            brief["story_id"] = str(params["story_id"])
            brief["source_uri"] = f"kronara://artifacts/{brief['story_id']}"
        return StoryBrief.from_dict(brief)

    def _story_worker(self, brief: StoryBrief, cancellation: threading.Event) -> None:
        run_id = f"story:{brief.story_id}"
        if cancellation.is_set():
            with self._lock:
                self._states[run_id] = self._run_state(run_id, "cancelled", 100, "cancelled")
            return
        with self._lock:
            self._states[run_id] = self._run_state(run_id, "running", 10, "guardian_input")
        worker_store = KronaraStore(self.database_path)
        worker_store.initialize()
        try:
            result = self._execute_story(brief, worker_store, update_state=False)
            with self._lock:
                self._states[run_id] = (
                    self._run_state(run_id, "cancelled", 100, "cancelled")
                    if cancellation.is_set()
                    else result
                )
        except Exception:
            with self._lock:
                self._states[run_id] = self._run_state(run_id, "failed", 100, "internal_error")
        finally:
            worker_store.close()

    def _execute_story(
        self,
        brief: StoryBrief,
        store: KronaraStore,
        *,
        update_state: bool = True,
    ) -> dict[str, Any]:
        result = StoryEngine(
            store=store,
            generator=DeterministicStoryProvider(),
            critic=DeterministicIndependentCritic(),
            cancellation_requested=self._cancellation_check(brief),
        ).run(brief)
        payload = {
            "schema_version": 1,
            "run_id": result.run_id,
            "status": result.status,
            "progress_percent": 100,
            "node": "guardian",
            "error_code": result.error_code,
            "concept_count": len(result.concepts),
            "scene_count": len(result.scenes),
            "word_count": result.script.word_count if result.script else 0,
            "tool_trace_ids": list(result.tool_trace_ids),
            "external_effect": False,
        }
        if update_state:
            with self._lock:
                self._states[result.run_id] = dict(payload)
        return payload

    def _cancellation_check(self, brief: StoryBrief) -> Callable[[], bool]:
        run_id = f"story:{brief.story_id}"
        with self._lock:
            event = self._cancellations.get(run_id)
        return event.is_set if event is not None else (lambda: False)

    @staticmethod
    def _run_state(run_id: str, status: str, progress: int, node: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "progress_percent": progress,
            "node": node,
            "external_effect": False,
        }

    @classmethod
    def _json(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json(item) for item in value]
        return value
