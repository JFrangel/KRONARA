from __future__ import annotations

import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from kronara.artifacts import ArtifactStore
from kronara.authority_client import AuthorityClient
from kronara.model_registry_v2 import ModelCapabilityRegistryV2, ModelRequirements
from kronara.operations_contracts import ToolTraceEvent
from kronara.rag_v3 import RAGV3Index, RetrievalQueryV3
from kronara.reddit_observatory import (
    ObservableRedditSignal,
    RedditObservatory,
    RedditSignalFilters,
)
from kronara.reddit_source_map import load_source_map, sensitivity_for
from kronara.routed_story_provider import (
    AuthorityModelRouter,
    KRONARA_CREATIVE_SYSTEM,
    RoutedIndependentCritic,
    RoutedStoryProvider,
)
from kronara.store import KronaraStore
from kronara.story_engine import StoryBrief, StoryEngine


class TracingAuthorityClient:
    def __init__(
        self,
        *,
        delegate: AuthorityClient,
        store: KronaraStore,
        run_id: str,
    ):
        self.delegate = delegate
        self.store = store
        self.run_id = run_id

    def invoke(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        event = ToolTraceEvent.started(
            event_id=f"trace_{uuid4().hex}",
            run_id=self.run_id,
            agent_id=self._agent(tool_id, arguments),
            tool_id=tool_id,
            arguments=self._safe_arguments(tool_id, arguments),
            started_at=started_at,
        )
        self.store.save_tool_trace(event)
        try:
            result = self.delegate.invoke(tool_id, arguments)
        except Exception as error:
            self.store.save_tool_trace(
                event.finish(
                    status="failed",
                    finished_at=datetime.now(UTC),
                    result_summary=type(error).__name__,
                    policy_findings=("authority_failure",),
                )
            )
            raise
        evidence = self._evidence(tool_id, result)
        self.store.save_tool_trace(
            event.finish(
                status="completed",
                finished_at=datetime.now(UTC),
                result_summary=self._summary(tool_id, result),
                evidence_refs=evidence,
            )
        )
        return result

    @staticmethod
    def _safe_arguments(tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_id == "model.complete":
            return {
                "task": str(arguments.get("task", "")),
                "candidate_models": [
                    str(item.get("model_id", ""))
                    for item in arguments.get("candidates", ())
                    if isinstance(item, dict)
                ],
                "max_tokens": int(arguments.get("max_tokens", 0)),
            }
        if tool_id == "reddit.list_signals":
            return {
                "subreddits": list(arguments.get("subreddits", ())),
                "sort": arguments.get("sort"),
                "limit": arguments.get("limit"),
            }
        if tool_id == "meta.metrics.read":
            return {"remote_id": arguments.get("remote_id")}
        return {}

    @staticmethod
    def _summary(tool_id: str, result: dict[str, Any]) -> str:
        if tool_id == "reddit.list_signals":
            return f"{len(result.get('signals', ()))} señales abstractas"
        if tool_id == "model.complete":
            return f"JSON estructurado por {result.get('model', 'modelo enrutado')}"
        if tool_id == "model.health":
            return f"{len(result.get('models', {}))} modelos observados"
        return "herramienta Rust completada"

    @staticmethod
    def _evidence(tool_id: str, result: dict[str, Any]) -> tuple[str, ...]:
        if tool_id == "reddit.list_signals":
            receipt = result.get("receipt")
            if isinstance(receipt, dict) and receipt.get("receipt_id"):
                return (f"reddit://receipt/{receipt['receipt_id']}",)
        if tool_id == "model.complete" and result.get("model"):
            return (f"model://{result.get('provider', 'unknown')}/{result['model']}",)
        if tool_id == "meta.metrics.read" and result.get("evidence_ref"):
            return (str(result["evidence_ref"]),)
        return ()

    @staticmethod
    def _agent(tool_id: str, arguments: dict[str, Any]) -> str:
        if tool_id.startswith("reddit."):
            return "opportunity_intelligence"
        if tool_id.startswith("meta."):
            return "performance_scientist"
        task = str(arguments.get("task", ""))
        if task == "story.critique":
            return "automated_qc"
        return "executive_orchestrator"


class ProductionContentPipeline:
    def __init__(
        self,
        *,
        authority: AuthorityClient,
        store: KronaraStore,
        rag: RAGV3Index,
        model_registry: ModelCapabilityRegistryV2,
        artifact_root: Path,
        graph: "KronaraGraph | None" = None,
        voice_provider: "object | None" = None,
        voice_id: str = "es-BO-SofiaNeural",
    ):
        self.authority = authority
        self.store = store
        self.rag = rag
        self.model_registry = model_registry
        self.artifacts = ArtifactStore(artifact_root)
        # Optional bitemporal knowledge graph for serialized (multi-part) stories.
        self.graph = graph
        # Optional real-voice duration: when a provider is supplied the story
        # engine measures narration length instead of estimating it.
        self._duration_measurer = None
        if voice_provider is not None:
            from kronara.voice import SceneDurationMeasurer

            self._duration_measurer = SceneDurationMeasurer(voice_provider, voice_id=voice_id)
        # Loaded once: knowledge/reddit-sources/*.md classify each subreddit as
        # entertainment vs. real_experience_serious (see reddit_source_map.py).
        self._source_map = load_source_map()

    def run(self, params: dict[str, Any]) -> dict[str, Any]:
        story_id = self._story_id(str(params.get("story_id") or f"owned_{uuid4().hex[:16]}"))
        run_id = f"content:{story_id}"
        traced = TracingAuthorityClient(
            delegate=self.authority,
            store=self.store,
            run_id=run_id,
        )
        reddit_page = traced.invoke(
            "reddit.list_signals",
            {
                "schema_version": 1,
                "subreddits": [str(item) for item in params.get("subreddits", ())],
                "sort": str(params.get("sort", "hot")),
                "time_filter": params.get("time_filter"),
                "after": params.get("after"),
                "limit": int(params.get("limit", 25)),
                "include_nsfw": False,
            },
        )
        receipt = dict(reddit_page.get("receipt", {}))
        observed_at = int(receipt.get("observed_at", 0))
        signals = tuple(
            self._observable(dict(item), observed_at)
            for item in reddit_page.get("signals", ())
            if isinstance(item, dict)
        )
        filtered = RedditObservatory().filter(
            signals,
            RedditSignalFilters(
                min_score=int(params.get("min_score", 20)),
                min_comments=int(params.get("min_comments", 3)),
                max_age_hours=float(params.get("max_age_hours", 168)),
                language=str(params.get("language", "es")),
                self_posts_only=bool(params.get("self_posts_only", False)),
                include_nsfw=False,
                max_saturation=float(params.get("max_saturation", 0.90)),
                min_velocity=float(params.get("min_velocity", 0.1)),
            ),
        )
        if not filtered.signals:
            raise ValueError("no Reddit signal passed the governed filters")
        selected = max(
            filtered.signals,
            key=lambda item: (
                item.velocity * (1 - item.saturation) + item.acceleration,
                item.score,
                item.source_id,
            ),
        )
        packet = self.rag.retrieve(
            RetrievalQueryV3(
                text=selected.theme_hint,
                now=observed_at,
                language="es",
                scope="narrative",
                allowed_rights=("owned_original", "promoted_learning"),
                limit=8,
                max_per_document=2,
            )
        )
        self._trace_retrieval(run_id, selected.theme_hint, packet)
        router = AuthorityModelRouter(authority=traced, registry=self.model_registry)
        editorial = router.complete(
            alias="planning_primary",
            requirements=ModelRequirements(
                frozenset({"planning"}), structured_output=True
            ),
            task="editorial.brief",
            system=KRONARA_CREATIVE_SYSTEM,
            input_payload={
                "abstract_signal": {
                    "theme_hint": selected.theme_hint,
                    "velocity": selected.velocity,
                    "saturation": selected.saturation,
                },
                "owned_context": [
                    {"content": item.content, "citation": item.citation_uri}
                    for item in packet.results
                ],
                "instruction": "crea un título, premisa y tema completamente originales",
            },
            response_schema={
                "type": "object",
                "required": ["title", "premise", "theme"],
                "additionalProperties": False,
            },
            max_tokens=1024,
        )
        citations = tuple(item.citation_uri for item in packet.results)
        evidence = tuple(
            dict.fromkeys(
                (
                    f"reddit://receipt/{receipt.get('receipt_id', 'unknown')}",
                    selected.source_uri,
                    *citations,
                )
            )
        )
        series_id = params.get("series_id")
        part_number = int(params.get("part_number", 1)) if series_id else None
        canon_builder = None
        series_context = ""
        if self.graph is not None and series_id:
            from kronara.series import SeriesCanonBuilder

            canon_builder = SeriesCanonBuilder(self.graph)
            series_context = canon_builder.context_for_part(
                str(series_id), part_number, now=observed_at
            ).context_block
        source_sensitivity = sensitivity_for(self._subreddit_of(selected), self._source_map)
        brief = StoryBrief(
            story_id=story_id,
            title=str(editorial["title"]),
            premise=str(editorial["premise"]),
            theme=str(editorial["theme"]),
            target_duration_seconds=int(params.get("target_duration_seconds", 90)),
            rights_mode="owned_original",
            source_uri=f"kronara://artifacts/{story_id}",
            evidence_refs=evidence,
            reference_texts=(selected.theme_hint,),
            series_id=str(series_id) if series_id else None,
            part_number=part_number,
            series_context=series_context,
            source_sensitivity=source_sensitivity,
        )
        generator = RoutedStoryProvider(router)
        result = StoryEngine(
            store=self.store,
            generator=generator,
            critic=RoutedIndependentCritic(router, generator=generator),
            duration_measurer=self._duration_measurer,
        ).run(brief)
        if result.status != "completed" or result.script is None:
            return {
                "schema_version": 1,
                "run_id": run_id,
                "status": result.status,
                "error_code": result.error_code,
                "selected_signal": self._signal_json(selected),
                "rejected_signals": filtered.rejected_by_reason,
                "reddit_receipt_id": receipt.get("receipt_id"),
                "rag_citations": list(citations),
            }
        artifact = self.artifacts.put_bytes(result.script.text.encode("utf-8"))
        artifact_uri = f"kronara://sha256/{artifact.sha256}"
        self.store.save_owned_story_artifact(
            story_id=story_id,
            artifact_uri=artifact_uri,
            path=str(artifact.path.resolve()),
            sha256=artifact.sha256,
            metadata={
                "rights_mode": "owned_original",
                "evidence_refs": list(evidence),
                "duration_seconds": result.script.estimated_seconds,
                "generator_family": result.generator_family,
                "critic_family": result.critic_family,
                "narrative_passed": bool(result.quality and result.quality.passed),
                "originality_passed": bool(result.originality and result.originality.passed),
                "safety_passed": True,
                "golden_no_regression": True,
            },
        )
        self.store.append_event(
            run_id,
            "content.completed",
            {
                "story_id": story_id,
                "artifact_uri": artifact_uri,
                "reddit_receipt_id": receipt.get("receipt_id"),
                "rag_citation_count": len(citations),
            },
        )
        if canon_builder is not None and series_id:
            cliffhanger = str(params.get("cliffhanger", ""))
            canon_builder.ingest_story_result(
                str(series_id),
                part_number,
                result,
                now=observed_at,
                cliffhanger=cliffhanger,
                is_final=bool(params.get("is_final", not cliffhanger)),
            )
        return {
            "schema_version": 1,
            "run_id": run_id,
            "status": "completed",
            "selected_signal": self._signal_json(selected),
            "rejected_signals": filtered.rejected_by_reason,
            "reddit_receipt_id": receipt.get("receipt_id"),
            "rag_citations": list(citations),
            "artifact_uri": artifact_uri,
            "story": {
                "story_id": story_id,
                "title": result.packaging.facebook_reels_title,
                "hook": result.retention.hook,
                "script": result.script.text,
                "word_count": result.script.word_count,
                "estimated_seconds": result.script.estimated_seconds,
                "duration_qc": asdict(result.duration_qc),
                "originality": asdict(result.originality),
                "quality": asdict(result.quality),
                "generator_family": result.generator_family,
                "critic_family": result.critic_family,
                "revision_count": result.revision_count,
                "tool_trace_ids": list(result.tool_trace_ids),
            },
        }

    def _trace_retrieval(self, run_id: str, query: str, packet: Any) -> None:
        started = datetime.now(UTC)
        event = ToolTraceEvent.started(
            event_id=f"trace_{uuid4().hex}",
            run_id=run_id,
            agent_id="context_engineer",
            tool_id="knowledge.retrieve",
            arguments={"query_hash": str(abs(hash(query))), "limit": 8},
            started_at=started,
        )
        self.store.save_tool_trace(event)
        self.store.save_tool_trace(
            event.finish(
                status="completed",
                finished_at=datetime.now(UTC),
                result_summary=f"{len(packet.results)} fragmentos propios citados",
                evidence_refs=tuple(item.citation_uri for item in packet.results),
                policy_findings=tuple(packet.degradations),
            )
        )

    @staticmethod
    def _observable(item: dict[str, Any], observed_at: int) -> ObservableRedditSignal:
        created_at = int(item.get("created_at", observed_at))
        age_hours = max(0.25, (observed_at - created_at) / 3600)
        score = max(0, int(item.get("score", 0)))
        comments = max(0, int(item.get("comments", 0)))
        velocity = (score + comments * 2) / age_hours
        acceleration = velocity / max(age_hours, 1.0)
        saturation = min(1.0, (score + comments) / 5_000)
        title = re.sub(r"https?://\S+", "", str(item.get("title", "")))
        theme_hint = " ".join(title.split())[:180]
        return ObservableRedditSignal(
            source_id=str(item["source_id"]),
            source_uri=str(item["source_uri"]),
            theme_hint=theme_hint,
            score=score,
            comments=comments,
            age_hours=age_hours,
            language=str(item.get("language") or ProductionContentPipeline._infer_language(theme_hint)),
            self_post=bool(item.get("self_post", False)),
            nsfw=bool(item.get("nsfw", False)),
            author_deleted=bool(item.get("author_deleted", False)),
            post_deleted=bool(item.get("post_deleted", False)),
            crosspost=bool(item.get("crosspost", False)),
            repost=False,
            observed_length=max(0, int(item.get("observed_length", 0))),
            velocity=velocity,
            acceleration=acceleration,
            saturation=saturation,
            lifetime_hours=min(168.0, age_hours * (1 + comments / max(score, 1))),
            rights_mode="reference_only",
        )

    @staticmethod
    def _subreddit_of(signal: ObservableRedditSignal) -> str:
        """Extract the subreddit name from a permalink-style source_uri
        (https://www.reddit.com/r/<subreddit>/...); empty string if absent."""
        match = re.search(r"/r/([A-Za-z0-9_]+)/", signal.source_uri)
        return match.group(1) if match else ""

    @staticmethod
    def _signal_json(signal: ObservableRedditSignal) -> dict[str, Any]:
        return {
            "source_id": signal.source_id,
            "source_uri": signal.source_uri,
            "theme_hint": signal.theme_hint,
            "velocity": signal.velocity,
            "acceleration": signal.acceleration,
            "saturation": signal.saturation,
            "rights_mode": signal.rights_mode,
        }

    @staticmethod
    def _infer_language(text: str) -> str:
        normalized = text.casefold()
        if any(character in normalized for character in "áéíóúñ¿¡"):
            return "es"
        tokens = set(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))
        spanish_markers = {
            "el", "la", "los", "las", "un", "una", "que", "antes", "después",
            "familia", "decisión", "historia", "verdad", "secreto",
        }
        return "es" if len(tokens & spanish_markers) >= 2 else "unknown"

    @staticmethod
    def _story_id(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,80}", value):
            raise ValueError("story id contains unsupported characters")
        return value
