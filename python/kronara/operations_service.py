from __future__ import annotations

import json
import hashlib
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from kronara.agent_catalog import AgentCatalog
from kronara.authority_client import AuthorityClient, UnavailableAuthorityClient
from kronara.content_pipeline import ProductionContentPipeline, TracingAuthorityClient
from kronara.embedding_registry import EmbeddingRegistry, ProductionEmbeddingFactory
from kronara.model_registry_v2 import ModelCapabilityRegistryV2
from kronara.observable_tools import ObservableToolRegistry
from kronara.operations_chat import OperationsChatAgent
from kronara.operations_contracts import OperationsChatRequest
from kronara.prompt_stack import AgentNarrativeProfile, PersonaProfile, PromptStackCompiler
from kronara.rag_v2 import IngestDocument
from kronara.resource_root import resource_root as _default_resource_root
from kronara.rag_v3 import RAGV3Index, RetrievalQueryV3
from kronara.store import KronaraStore
from kronara.performance import MetricSnapshot
from kronara.performance_learning import PerformanceLearningService
from kronara.story_reuse import StoryExampleRepository, StoryQualityEvidence
from kronara.training_rights import RightsMode, TrainingAsset
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

    def __init__(
        self,
        data_dir: Path,
        *,
        resource_root: Path | None = None,
        authority: AuthorityClient | None = None,
        embedding_alias: str = "bge_m3",
        reranker_alias: str | None = "bge_reranker_v2_m3",
        voice_provider: "object | None" = None,
        voice_id: str = "es-BO-SofiaNeural",
        image_provider: "object | None" = None,
        renderer: "object | None" = None,
        visual_style_registry: "object | None" = None,
        asset_library: "object | None" = None,
        opportunity_store: "object | None" = None,
        rate_learner: "object | None" = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.resource_root = resource_root or _default_resource_root()
        self.authority = authority or UnavailableAuthorityClient()
        self.embedding_alias = embedding_alias
        self.reranker_alias = reranker_alias
        self.database_path = self.data_dir / "kronara.db"
        self.store = KronaraStore(self.database_path)
        self.store.initialize()
        self._states: dict[str, dict[str, Any]] = {}
        self._cancellations: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._paused = False
        # Chat can only ever PROPOSE an action (see OperationsChatAgent);
        # action.approve executes one by its idempotency_key, never by
        # arguments the client resupplies -- otherwise a compromised
        # frontend (or an injected chat reply) could execute an arbitrary
        # content.run with attacker-chosen params. Popped on approval, so
        # each proposal is single-use.
        self._pending_intents: dict[str, dict[str, Any]] = {}
        self._model_registry = ModelCapabilityRegistryV2.load(
            self.resource_root / "config" / "models" / "registry.v2.json"
        )
        self._rag = self._build_rag()
        self._chat = self._build_chat()
        # V8 visual production stack -- all optional; content_run() degrades
        # to text-only when any of these are unavailable on this machine
        # (no ffmpeg, no local SDXL weights). See ProductionContentPipeline
        # for the actual degrade-gracefully logic.
        self._voice_provider = voice_provider
        self._voice_id = voice_id
        self._image_provider = image_provider
        self._renderer = renderer
        self._visual_style_registry = visual_style_registry
        self._asset_library = asset_library
        self._opportunity_store = opportunity_store
        self._rate_learner = rate_learner

    def methods(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        return {
            "operations.chat": self.operations_chat,
            "operations.context": self.operations_context,
            "tools.timeline": self.tool_timeline,
            "memory.search": self.memory_search,
            "rag.retrieve_v3": self.rag_retrieve,
            "story.test": self.story_test,
            "content.run": self.content_run,
            "performance.learn": self.performance_learn,
            "run.cancel": self.cancel,
            "run.progress": self.progress,
            "operations.control_snapshot": self.control_snapshot,
            "programs.list": self.programs_list,
            "episodes.list": self.episodes_list,
            "schedule.tick": self.schedule_tick,
            "action.approve": self.action_approve,
        }

    def schedule_tick(self, params: dict[str, Any]) -> dict[str, Any]:
        """B1: the autonomous weekly grid's real trigger. Rust's background
        timer calls this with the current wall-clock time (see spawn_
        schedule_ticker in lib.rs) exactly like any other RPC method --
        AutonomousProductionLoop.tick() does the rest, reusing content_run()
        (the same method the UI's "Crear historia gobernada" button calls)
        as run_program so a scheduled episode and a manually-triggered one
        go through the identical, already-proven pipeline."""
        from kronara.autonomous_loop import AutonomousProductionLoop
        from kronara.contracts import AutonomyMode, AutonomyPolicy
        from kronara.programs import ProgramRegistry, default_registry_path
        from kronara.schedule import AutonomousRunAuthorizer, Scheduler, derive_schedule_rules

        now = int(params["now"])
        registry = ProgramRegistry.load(default_registry_path())
        rules = derive_schedule_rules(registry.get(pid) for pid in registry.program_ids)
        loop = AutonomousProductionLoop(
            scheduler=Scheduler(rules),
            authorizer=AutonomousRunAuthorizer(AutonomyPolicy(mode=AutonomyMode.FULL_AUTO)),
            registry=registry,
            store=self.store,
            run_program=lambda _program_id, run_params: self.content_run(run_params),
            is_paused=lambda: self._paused,
        )
        report = loop.tick(now)
        return {
            "schema_version": 1,
            "checked_at": report.checked_at,
            "ran": list(report.ran),
            "outcomes": [
                {
                    "program_id": outcome.program_id,
                    "rule_id": outcome.rule_id,
                    "status": outcome.status,
                    "detail": outcome.detail,
                }
                for outcome in report.outcomes
            ],
        }

    def episodes_list(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 50))
        program_id = params.get("program_id")
        episodes = self.store.list_owned_story_artifacts(
            limit=limit, program_id=str(program_id) if program_id else None
        )
        return {
            "schema_version": 1,
            "episodes": [
                {
                    "story_id": episode["story_id"],
                    "title": episode["metadata"].get("title", episode["story_id"]),
                    "program_id": episode["program_id"] or None,
                    "created_at": episode["created_at"],
                    "duration_seconds": episode["metadata"].get("duration_seconds"),
                    "generator_family": episode["metadata"].get("generator_family"),
                    "critic_family": episode["metadata"].get("critic_family"),
                    "narrative_passed": episode["metadata"].get("narrative_passed"),
                    "originality_passed": episode["metadata"].get("originality_passed"),
                    "video_status": episode["metadata"].get("video_status"),
                    "video_path": episode["metadata"].get("video_path") or None,
                    "cover_image_path": episode["metadata"].get("cover_image_path") or None,
                    "video_qc_passed": episode["metadata"].get("video_qc_passed"),
                }
                for episode in episodes
            ],
        }

    def programs_list(self, _: dict[str, Any]) -> dict[str, Any]:
        from kronara.programs import ProgramRegistry, default_registry_path

        registry = ProgramRegistry.load(default_registry_path())
        return {
            "schema_version": 1,
            "programs": [
                {
                    "program_id": program.program_id,
                    "name": program.name,
                    "weekday": program.weekday,
                    "genre": program.genre,
                    "description": program.description,
                    "visual_style_id": program.visual_style_id,
                    "target_duration_seconds": program.target_duration_seconds,
                    "platforms": list(program.platforms),
                }
                for program in (registry.get(pid) for pid in registry.program_ids)
            ],
        }

    def operations_chat(self, params: dict[str, Any]) -> dict[str, Any]:
        request = OperationsChatRequest(
            schema_version=int(params.get("schema_version", 1)),
            request_id=str(params["request_id"]),
            conversation_id=str(params["conversation_id"]),
            message=str(params["message"]),
            minimum_context_coverage=float(params.get("minimum_context_coverage", 0.7)),
        )
        response = self._chat.answer(request)
        if response.action_intent is not None:
            with self._lock:
                self._pending_intents[response.action_intent.idempotency_key] = asdict(
                    response.action_intent
                )
        return self._json(asdict(response))

    def action_approve(self, params: dict[str, Any]) -> dict[str, Any]:
        idempotency_key = str(params["idempotency_key"])
        with self._lock:
            intent = self._pending_intents.pop(idempotency_key, None)
        if intent is None:
            return {"schema_version": 1, "status": "not_found", "kind": None, "result": None}
        if intent["kind"] == "create_episode":
            story_id = f"owned_chat_{uuid4().hex[:16]}"
            result = self.content_run({**intent["arguments"], "story_id": story_id})
            return {"schema_version": 1, "status": "executed", "kind": intent["kind"], "result": result}
        return {"schema_version": 1, "status": "unsupported", "kind": intent["kind"], "result": None}

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
            dict.fromkeys((*payload["degradations"], *self._rag_degradations))
        )
        return payload

    def content_run(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._paused:
                raise ValueError("global pause blocks content runs")
        params = self._resolve_program_defaults(params)
        return ProductionContentPipeline(
            authority=self.authority,
            store=self.store,
            rag=self._rag,
            model_registry=self._model_registry,
            artifact_root=self.data_dir / "artifacts",
            voice_provider=self._voice_provider,
            voice_id=self._voice_id,
            image_provider=self._image_provider,
            renderer=self._renderer,
            visual_style_registry=self._visual_style_registry,
            asset_library=self._asset_library,
            opportunity_store=self._opportunity_store,
            rate_learner=self._rate_learner,
        ).run(params)

    @staticmethod
    def _resolve_program_defaults(params: dict[str, Any]) -> dict[str, Any]:
        """When the caller names a program_id but doesn't already supply
        subreddits (the UI's "create an episode for this program" action,
        as opposed to Estudio's free-text manual test), derive them the
        same way the autonomous scheduler already does for its own weekly
        runs -- see autonomous_loop.py's _fire(). A caller that already
        knows exactly what it wants (produce_episode.rs, the manual test
        flow) is left untouched."""
        program_id = params.get("program_id")
        if not program_id or params.get("subreddits"):
            return params
        from kronara.programs import ProgramRegistry, default_registry_path
        from kronara.reddit_source_map import subreddits_for_program

        program = ProgramRegistry.load(default_registry_path()).get(str(program_id))
        resolved = dict(params)
        resolved.setdefault("subreddits", list(subreddits_for_program(str(program_id))))
        resolved.setdefault("target_duration_seconds", program.target_duration_seconds)
        resolved.setdefault("sort", "hot")
        resolved.setdefault("limit", 25)
        return resolved

    def performance_learn(self, params: dict[str, Any]) -> dict[str, Any]:
        story_id = str(params["story_id"])
        artifact = self.store.load_owned_story_artifact(story_id)
        path = Path(str(artifact["path"]))
        content = path.read_text(encoding="utf-8")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != artifact["sha256"]:
            raise ValueError("owned story artifact hash mismatch")
        traced = TracingAuthorityClient(
            delegate=self.authority,
            store=self.store,
            run_id=f"performance:{story_id}",
        )
        receipt = traced.invoke(
            "meta.metrics.read", {"remote_id": str(params["remote_id"])}
        )
        metrics = dict(receipt.get("metrics", {}))
        observed_at = datetime.fromtimestamp(int(receipt["observed_at"]), UTC)
        published_at = datetime.fromisoformat(str(params["published_at"]))
        plays = max(0, int(metrics.get("plays", 0)))
        reach = max(plays, int(metrics.get("reach", plays)))
        completions = min(plays, max(0, int(metrics.get("completions", 0))))
        average_watch_ms = max(0.0, float(metrics.get("average_watch_time_ms", 0)))
        target = MetricSnapshot(
            schema_version=1,
            snapshot_id=str(receipt["evidence_ref"]),
            content_id=story_id,
            platform="facebook",
            published_at=published_at,
            observed_at=observed_at,
            metric_window_hours=max(
                1, round((observed_at - published_at).total_seconds() / 3600)
            ),
            impressions=reach,
            starts=plays,
            completions=completions,
            replays=max(0, int(metrics.get("replays", 0))),
            shares=max(0, int(metrics.get("shares", 0))),
            watch_time_seconds=average_watch_ms / 1000 * plays,
            duration_seconds=float(params["duration_seconds"]),
            voice_id=str(params["voice_id"]),
            topic=str(params["topic"]),
            hook_id=str(params["hook_id"]),
            publication_hour=int(params["publication_hour"]),
            audience_segment=str(params["audience_segment"]),
        )
        cohort = tuple(
            self._metric_snapshot(dict(item))
            for item in params.get("cohort_snapshots", ())
        )
        snapshots = (target, *cohort)
        for snapshot in snapshots:
            payload = asdict(snapshot)
            payload["published_at"] = snapshot.published_at.isoformat()
            payload["observed_at"] = snapshot.observed_at.isoformat()
            self.store.save_metric_snapshot(payload)
        metadata = dict(artifact["metadata"])
        quality = StoryQualityEvidence(
            narrative_passed=bool(metadata.get("narrative_passed", False)),
            originality_passed=bool(metadata.get("originality_passed", False)),
            safety_passed=bool(metadata.get("safety_passed", False)),
            publication_succeeded=True,
            golden_no_regression=bool(metadata.get("golden_no_regression", False)),
            evidence_refs=(
                str(receipt["evidence_ref"]),
                f"artifact://sha256/{artifact['sha256']}",
            ),
        )
        learned = PerformanceLearningService(
            repository=StoryExampleRepository(store=self.store, index=self._rag)
        ).learn(
            target_story_id=story_id,
            snapshots=snapshots,
            quality=quality,
            asset=TrainingAsset(
                asset_id=story_id,
                rights_mode=RightsMode.OWNED_ORIGINAL,
                source_uri=f"kronara://artifacts/{story_id}",
            ),
            content=content,
        )
        return self._json(
            {
                "schema_version": 1,
                "diagnosis": asdict(learned.diagnosis),
                "performance": asdict(learned.performance),
                "decision": asdict(learned.decision),
            }
        )

    def story_test(self, params: dict[str, Any]) -> dict[str, Any]:
        if bool(params.get("wait", False)):
            raise ValueError("synchronous story execution is not permitted")
        brief = self._story_brief(params)
        run_id = f"story:{brief.story_id}"
        cancellation = threading.Event()
        with self._lock:
            if self._paused:
                blocked = self._run_state(
                    run_id, "blocked", 0, "global_pause", error_code="GLOBAL_PAUSE"
                )
                self._states[run_id] = blocked
                return dict(blocked)
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
            if paused:
                for run_id, event in self._cancellations.items():
                    event.set()
                    current = self._states.get(run_id)
                    if current and current["status"] in {"queued", "running"}:
                        self._states[run_id] = self._run_state(
                            run_id,
                            "cancellation_requested",
                            int(current["progress_percent"]),
                            str(current["node"]),
                            error_code="GLOBAL_PAUSE",
                        )
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
        narrative_profile = AgentCatalog.load_narrative_profile(
            "operations_chat",
            self.resource_root / "config" / "agents",
            self.resource_root / "config" / "personas",
        )
        if narrative_profile is None:
            narrative_payload = json.loads(
                (self.resource_root / "config" / "personas" / "operations_chat.v1.json").read_text(
                    encoding="utf-8"
                )
            )
            narrative_profile = AgentNarrativeProfile.from_dict(narrative_payload)
        from kronara.programs import ProgramRegistry, default_registry_path

        registry = ProgramRegistry.load(default_registry_path())
        programs = tuple(registry.get(pid) for pid in registry.program_ids)
        return OperationsChatAgent(
            tools=tools,
            store=self.store,
            prompt_compiler=PromptStackCompiler(),
            persona=PersonaProfile.from_dict(persona_payload),
            responder=LocalOperationsResponder(),
            narrative_profile=narrative_profile,
            programs=programs,
        )

    def _build_rag(self) -> RAGV3Index:
        registry = EmbeddingRegistry.load(
            self.resource_root / "config" / "models" / "embeddings.v1.json"
        )
        runtime = ProductionEmbeddingFactory(registry).build(
            self.embedding_alias,
            reranker_alias=self.reranker_alias,
        )
        descriptor = runtime.descriptor
        self._rag_degradations = runtime.degradations
        index = RAGV3Index(
            self.data_dir / "knowledge.db",
            descriptor,
            runtime.embedder,
            reranker=runtime.reranker,
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

    @staticmethod
    def _metric_snapshot(params: dict[str, Any]) -> MetricSnapshot:
        return MetricSnapshot(
            schema_version=int(params["schema_version"]),
            snapshot_id=str(params["snapshot_id"]),
            content_id=str(params["content_id"]),
            platform=str(params["platform"]),
            published_at=datetime.fromisoformat(str(params["published_at"])),
            observed_at=datetime.fromisoformat(str(params["observed_at"])),
            metric_window_hours=int(params["metric_window_hours"]),
            impressions=int(params["impressions"]),
            starts=int(params["starts"]),
            completions=int(params["completions"]),
            replays=int(params["replays"]),
            shares=int(params["shares"]),
            watch_time_seconds=float(params["watch_time_seconds"]),
            duration_seconds=float(params["duration_seconds"]),
            voice_id=str(params["voice_id"]),
            topic=str(params["topic"]),
            hook_id=str(params["hook_id"]),
            publication_hour=int(params["publication_hour"]),
            audience_segment=str(params["audience_segment"]),
        )

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
    def _run_state(
        run_id: str,
        status: str,
        progress: int,
        node: str,
        *,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "progress_percent": progress,
            "node": node,
            "external_effect": False,
            "error_code": error_code,
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
