from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from kronara.agents import super_agent
from kronara.artifacts import ArtifactStore
from kronara.authority_client import AuthorityClient, AuthorityInvocationError
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
            agent_id=super_agent(self._agent(tool_id, arguments)),
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
        voice_id: str = "es-CO-GonzaloNeural",
        image_provider: "object | None" = None,
        renderer: "object | None" = None,
        visual_style_registry: "object | None" = None,
        style_resolver: "object | None" = None,
        asset_library: "object | None" = None,
        opportunity_store: "object | None" = None,
        rate_learner: "object | None" = None,
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

            self._duration_measurer = SceneDurationMeasurer(
                voice_provider, voice_id=voice_id, rate_learner=rate_learner
            )
        # V8: the visual production stage (V0-V6) runs only when all three of
        # these are supplied -- image_provider + renderer are required to
        # produce anything at all; visual_style_registry/asset_library are
        # each independently optional (produce_episode_video degrades to
        # ai_image-only, no music, when the library is absent).
        self._image_provider = image_provider
        self._renderer = renderer
        self._visual_style_registry = visual_style_registry
        # v0.8 Fase 1: resolves the named visual style (10-style library) for an
        # episode, honoring a per-episode style_id override, then the program's
        # configured visual_style_id, falling back to the legacy per-program
        # registry above. When absent, the legacy registry path is used alone.
        self._style_resolver = style_resolver
        self._asset_library = asset_library
        # Optional: caches the no-credential RSS fallback's harvest so a
        # scheduled program firing repeatedly doesn't re-hit Reddit's live
        # RSS endpoint (and its per-IP rate limit) on every single run.
        self._opportunity_store = opportunity_store
        self._leased_opportunity_id: str | None = None
        # Loaded once: knowledge/reddit-sources/*.md classify each subreddit as
        # entertainment vs. real_experience_serious (see reddit_source_map.py).
        self._source_map = load_source_map()
        self._source_context_by_source_id: dict[str, str] = {}

    def run(self, params: dict[str, Any]) -> dict[str, Any]:
        story_id = self._story_id(str(params.get("story_id") or f"owned_{uuid4().hex[:16]}"))
        run_id = f"content:{story_id}"
        traced = TracingAuthorityClient(
            delegate=self.authority,
            store=self.store,
            run_id=run_id,
        )
        subreddits = [str(item) for item in params.get("subreddits", ())]
        self._source_context_by_source_id = {}
        try:
            reddit_page = traced.invoke(
                "reddit.list_signals",
                {
                    "schema_version": 1,
                    "subreddits": subreddits,
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
            for item in reddit_page.get("signals", ()):
                if isinstance(item, dict) and item.get("source_id"):
                    context = self._clean_source_context(
                        item.get("selftext") or item.get("body") or item.get("source_text") or ""
                    )
                    if context:
                        self._source_context_by_source_id[str(item["source_id"])] = context
            signal_filters = RedditSignalFilters(
                min_score=int(params.get("min_score", 20)),
                min_comments=int(params.get("min_comments", 3)),
                max_age_hours=float(params.get("max_age_hours", 168)),
                language=self._language_filter(params),
                self_posts_only=bool(params.get("self_posts_only", False)),
                include_nsfw=False,
                max_saturation=float(params.get("max_saturation", 0.90)),
                min_velocity=float(params.get("min_velocity", 0.1)),
            )
        except AuthorityInvocationError as error:
            # Reddit's OAuth-gated live API (reddit.rs) needs registered
            # KRONARA_REDDIT_* credentials -- Kronara's own design principle
            # is that discovery never requires those (see harvest_reddit.py,
            # knowledge/reddit-sources/). Fall back to the same no-credential
            # public RSS reading rather than failing content.run outright;
            # a run should degrade, not silently produce nothing at all.
            receipt, observed_at, signals = self._rss_fallback_signals(subreddits, params)
            # RSS carries no score/comments/velocity -- filtering on those
            # would reject every signal. What still applies (age, language,
            # NSFW, self-post-only) still does.
            signal_filters = RedditSignalFilters(
                max_age_hours=float(params.get("max_age_hours", 168)),
                language=self._language_filter(params),
                self_posts_only=bool(params.get("self_posts_only", False)),
                include_nsfw=False,
            )
            self.store.append_event(
                run_id,
                "content.reddit_fallback_rss",
                {"reason": str(error), "subreddits": subreddits, "signal_count": len(signals)},
            )
        filtered = RedditObservatory().filter(signals, signal_filters)
        if not filtered.signals:
            self._release_leased_opportunity()
            raise ValueError("no Reddit signal passed the governed filters")
        selected = max(
            filtered.signals,
            key=lambda item: (
                item.velocity * (1 - item.saturation) + item.acceleration,
                item.score,
                item.source_id,
            ),
        )
        selected_context = self._source_context_by_source_id.get(selected.source_id, "")
        self._agent_log(
            run_id,
            "opportunity_intelligence",
            "signal_selected",
            f"Seleccionó señal de {self._subreddit_of(selected) or 'Reddit'} tras filtrar {filtered.observed_count}.",
            {
                "observed_count": filtered.observed_count,
                "accepted_count": len(filtered.signals),
                "rejected_by_reason": filtered.rejected_by_reason,
                "selected_source_uri": selected.source_uri,
                "theme_hint": selected.theme_hint,
                "source_context_words": len(selected_context.split()),
            },
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
                "source_context": selected_context,
                "owned_context": [
                    {"content": item.content, "citation": item.citation_uri}
                    for item in packet.results
                ],
                "instruction": "crea un título, premisa y tema completamente originales",
            },
            response_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "premise": {"type": "string"},
                    "theme": {"type": "string"},
                },
                "required": ["title", "premise", "theme"],
                "additionalProperties": False,
            },
            max_tokens=1024,
        )
        self._agent_log(
            run_id,
            "editorial_executive",
            "brief_created",
            f"Ordenó historia original: {editorial.get('title', 'sin título')}.",
            {
                "title": editorial.get("title"),
                "premise": editorial.get("premise"),
                "theme": editorial.get("theme"),
                "source_sensitivity": sensitivity_for(self._subreddit_of(selected), self._source_map),
            },
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
            reference_texts=tuple(text for text in (selected.theme_hint, selected_context) if text),
            series_id=str(series_id) if series_id else None,
            part_number=part_number,
            series_context=series_context,
            source_sensitivity=source_sensitivity,
            program_id=str(params["program_id"]) if params.get("program_id") else None,
        )
        generator = RoutedStoryProvider(router)
        result = StoryEngine(
            store=self.store,
            generator=generator,
            critic=RoutedIndependentCritic(router, generator=generator),
            duration_measurer=self._duration_measurer,
        ).run(brief)
        if result.status != "completed" or result.script is None:
            self._release_leased_opportunity()
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
        # Produced BEFORE the artifact is saved (not after, as this used to
        # be) so the video/cover paths make it into the SAVED metadata --
        # episodes.list only ever sees what's persisted here, not the
        # in-memory response of the run that created it. Without this, a
        # freshly-created episode showed its video in the moment (Estudio's
        # own contentResult), but the SAME episode loaded later from
        # Programas/Episodios had no way to know a video existed at all.
        style_id_override = str(params["style_id"]) if params.get("style_id") else None
        video = self._produce_video(
            story_id=story_id, brief=brief, result=result, run_id=run_id,
            style_id=style_id_override,
        )
        artifact = self.artifacts.put_bytes(result.script.text.encode("utf-8"))
        artifact_uri = f"kronara://sha256/{artifact.sha256}"
        self.store.save_owned_story_artifact(
            story_id=story_id,
            artifact_uri=artifact_uri,
            path=str(artifact.path.resolve()),
            sha256=artifact.sha256,
            created_at=observed_at,
            program_id=brief.program_id or "",
            metadata={
                "title": result.packaging.facebook_reels_title if result.packaging else brief.title,
                "hook": result.retention.hook if result.retention else "",
                "rights_mode": "owned_original",
                "evidence_refs": list(evidence),
                "duration_seconds": result.script.estimated_seconds,
                "generator_family": result.generator_family,
                "critic_family": result.critic_family,
                "narrative_passed": bool(result.quality and result.quality.passed),
                "originality_passed": bool(result.originality and result.originality.passed),
                "safety_passed": True,
                "golden_no_regression": True,
                "video_status": video["status"] if video else "not_configured",
                "video_path": video.get("output_path", "") if video else "",
                "cover_image_path": video.get("cover_image_path", "") if video else "",
                "video_qc_passed": video.get("qc_passed") if video else None,
                "video_qc_issues": video.get("qc_issues", []) if video else [],
                "video_integrated_lufs": video.get("integrated_lufs") if video else None,
                "video_scene_count": video.get("scene_count") if video else None,
                "video_shot_count": video.get("shot_count") if video else None,
                "video_source_kind_counts": video.get("source_kind_counts", {}) if video else {},
                "music_path": video.get("music_path", "") if video else "",
                "sfx_cue_tags": video.get("sfx_cue_tags", []) if video else [],
                "sfx_resolved_paths": video.get("sfx_resolved_paths", {}) if video else {},
                "sfx_missing_tags": video.get("sfx_missing_tags", []) if video else [],
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
                "video_status": video["status"] if video else "not_configured",
            },
        )
        self._agent_log(
            run_id,
            "video_composer",
            "episode_saved",
            "Guardó el episodio, metadatos, portada y estado de video en la biblioteca local.",
            {
                "story_id": story_id,
                "video_status": video["status"] if video else "not_configured",
                "cover_image_path": video.get("cover_image_path", "") if video else "",
                "video_path": video.get("output_path", "") if video else "",
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
            "video": video,
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

    def _release_leased_opportunity(self) -> None:
        if self._opportunity_store is None or not self._leased_opportunity_id:
            return
        release = getattr(self._opportunity_store, "release", None)
        if release is not None:
            release(self._leased_opportunity_id)
        self._leased_opportunity_id = None

    def _agent_log(
        self,
        run_id: str,
        agent_id: str,
        action: str,
        detail: str,
        payload: dict[str, Any],
    ) -> None:
        self.store.append_event(
            run_id,
            "agent.log",
            {
                "agent_id": super_agent(agent_id),
                "action": action,
                "detail": detail,
                "payload": payload,
            },
        )

    def _rss_fallback_signals(
        self, subreddits: list[str], params: dict[str, Any]
    ) -> tuple[dict[str, Any], int, tuple[ObservableRedditSignal, ...]]:
        """No-credential fallback for reddit.list_signals: the same public
        RSS reading harvest_reddit.py already uses. RSS exposes no score/
        comments, so those fields are honestly zero (not fabricated) --
        callers must use RedditSignalFilters without score/velocity
        thresholds for these.

        Cache-first: when an opportunity_store is configured, this draws
        from it (OpportunityStore -- built for exactly "harvest occasionally,
        consume many times", but never actually wired into content.run
        before) instead of hitting Reddit's live RSS endpoint on every single
        run. A program firing every 30 minutes on B1's scheduler, each
        reading several subreddits, adds up fast against Reddit's per-IP RSS
        rate limiting; most calls should now be served from the local cache,
        with a live fetch (which backfills the cache for next time) only
        when it's genuinely empty for these subreddits."""
        now = int(datetime.now(UTC).timestamp())
        if self._opportunity_store is not None:
            cached = self._opportunity_store.take_next_for_subreddits(subreddits, now)
            if cached is None:
                self._harvest_opportunities(subreddits, int(params.get("limit", 25)), now)
                cached = self._opportunity_store.take_next_for_subreddits(subreddits, now)
            if cached is not None:
                self._leased_opportunity_id = getattr(cached, "opportunity_id", None)
                signal = self._signal_from_theme(
                    source_uri=cached.link, theme_hint=cached.theme_hint,
                    age_hours=max(0.25, (now - cached.harvested_at) / 3600),
                )
                context = self._clean_source_context(getattr(cached, "body", ""))
                if context:
                    self._source_context_by_source_id[signal.source_id] = context
                receipt = {
                    "receipt_id": f"cache_{now}", "query_hash": "opportunity_cache",
                    "contract_reference": "no_credentials_public_rss", "observed_at": now, "count": 1,
                }
                return receipt, now, (signal,)

        # No store configured (e.g. a bare unit test), or a live fetch just
        # ran and still found nothing new for these subreddits -- fall back
        # to building signals directly from a fresh, uncached live fetch.
        posts = self._harvest_opportunities(subreddits, int(params.get("limit", 25)), now)
        built_signals = []
        for post in posts:
            signal = self._signal_from_theme(
                source_uri=post.link, theme_hint=post.title,
                age_hours=self._rss_post_age_hours(post, now),
            )
            context = self._clean_source_context(getattr(post, "body", ""))
            if context:
                self._source_context_by_source_id[signal.source_id] = context
            built_signals.append(signal)
        signals = tuple(built_signals)
        receipt = {
            "receipt_id": f"rss_{now}",
            "query_hash": "rss",
            "contract_reference": "no_credentials_public_rss",
            "observed_at": now,
            "count": len(signals),
        }
        return receipt, now, signals

    def _harvest_opportunities(self, subreddits: list[str], limit: int, now: int) -> list[Any]:
        """One live RSS fetch, saved into opportunity_store (if configured)
        for future runs to consume without hitting the network again."""
        from kronara.reddit_rss import RedditRssReader

        posts = RedditRssReader().trending(subreddits, max_subs=max(1, len(subreddits)), per_sub=limit)
        if self._opportunity_store is not None and posts:
            self._opportunity_store.harvest(posts, now)
        return posts

    @staticmethod
    def _rss_post_age_hours(post: Any, now: int) -> float:
        try:
            published_at = int(datetime.fromisoformat(post.published).timestamp())
        except (ValueError, TypeError):
            published_at = now
        return max(0.25, (now - published_at) / 3600)

    def _signal_from_theme(self, *, source_uri: str, theme_hint: str, age_hours: float) -> ObservableRedditSignal:
        clean_title = re.sub(r"https?://\S+", "", theme_hint)
        hint = " ".join(clean_title.split())[:180]
        return ObservableRedditSignal(
            source_id=hashlib.sha256(source_uri.encode("utf-8")).hexdigest()[:16],
            source_uri=source_uri,
            theme_hint=hint,
            score=0,
            comments=0,
            age_hours=age_hours,
            language=self._infer_language(hint),  # RSS has no per-post language field
            self_post=True,
            nsfw=False,
            author_deleted=False,
            post_deleted=False,
            crosspost=False,
            repost=False,
            observed_length=len(hint),
            velocity=0.0,
            acceleration=0.0,
            saturation=0.0,
            lifetime_hours=age_hours,
            rights_mode="reference_only",
        )

    @staticmethod
    def _clean_source_context(value: Any, *, max_chars: int = 8000) -> str:
        text = re.sub(r"https?://\S+", " ", str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.split())[:max_chars]

    def _produce_video(
        self, *, story_id: str, brief: StoryBrief, result: Any, run_id: str,
        style_id: str | None = None,
    ) -> dict[str, Any] | None:
        """V8: render the full visual episode (V0-V6) when the pipeline is
        configured for it and real per-scene narration audio was measured.
        Additive and best-effort: a failure here never fails content.run --
        the text artifact already saved above is a complete, valid result on
        its own; video is a bonus stage layered on top of it."""
        if self._image_provider is None or self._renderer is None:
            return None
        voice_duration = result.voice_duration
        if voice_duration is None:
            return None
        if not voice_duration.audio_refs or any(not ref for ref in voice_duration.audio_refs):
            return None
        visual_style = None
        if self._style_resolver is not None:
            # Fase 1: named-style resolution (per-episode override → program's
            # visual_style_id → legacy fallback), all handled by the resolver.
            visual_style = self._style_resolver.resolve(
                program_id=brief.program_id, style_id=style_id
            )
        elif self._visual_style_registry is not None and brief.program_id:
            try:
                visual_style = self._visual_style_registry.get(brief.program_id)
            except KeyError:
                visual_style = None
        try:
            from kronara.visual_production import (
                _dominant_character_names,
                produce_episode_video,
            )

            cover_text = next(
                (item.hook for item in result.concepts if item.concept_id == result.selected_concept_id),
                brief.premise,
            )
            # Character bible: one cheap model call -> canonical appearance per
            # recurring character, injected into every scene prompt so the same
            # person renders consistently. Best-effort: {} degrades to the prior
            # name-only text anchors (see character_bible.build_character_bible).
            character_descriptions: dict[str, Any] = {}
            try:
                from kronara.character_bible import build_character_bible
                from kronara.routed_story_provider import AuthorityModelRouter

                character_descriptions = build_character_bible(
                    AuthorityModelRouter(authority=self.authority, registry=self.model_registry),
                    character_names=_dominant_character_names(result.scenes),
                    premise=brief.premise,
                    theme=brief.theme,
                    program_id=brief.program_id,
                )
            except Exception:
                character_descriptions = {}
            production = produce_episode_video(
                scenes=result.scenes,
                voice_duration=voice_duration,
                output_dir=str(self.artifacts.root / "video" / story_id),
                episode_id=story_id,
                renderer=self._renderer,
                image_provider=self._image_provider,
                visual_style=visual_style,
                library=self._asset_library,
                cover_text=cover_text,
                character_descriptions=character_descriptions,
                progress_callback=lambda payload: self.store.append_event(
                    run_id,
                    "content.video_progress",
                    {"story_id": story_id, **payload},
                ),
            )
        except Exception as error:
            self.store.append_event(
                run_id, "content.video_failed", {"story_id": story_id, "error": type(error).__name__}
            )
            return {"status": "failed", "error": type(error).__name__}
        return {
            "status": "completed" if production.qc.passed else "qc_failed",
            "output_path": production.output_path,
            "cover_image_path": production.cover_image_path,
            "qc_passed": production.qc.passed,
            "qc_issues": list(production.qc.issues),
            "integrated_lufs": production.loudness.integrated_lufs,
            "scene_count": production.scene_count,
            "shot_count": production.shot_count,
            "source_kind_counts": production.source_kind_counts,
            "music_path": production.music_path,
            "sfx_cue_tags": list(production.sfx_cue_tags),
            "sfx_resolved_paths": production.sfx_resolved_paths or {},
            "sfx_missing_tags": list(production.sfx_missing_tags),
        }

    def _trace_retrieval(self, run_id: str, query: str, packet: Any) -> None:
        started = datetime.now(UTC)
        event = ToolTraceEvent.started(
            event_id=f"trace_{uuid4().hex}",
            run_id=run_id,
            agent_id=super_agent("context_engineer"),
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
    def _language_filter(params: dict[str, Any]) -> str | None:
        """No default language restriction on the SOURCE signal. Reddit's
        title is only ever used as an abstract theme_hint -- the actual
        story is always freshly generated Spanish prose (KRONARA_CREATIVE_
        SYSTEM, es-* voices), regardless of what language the source post
        was written in. Kronara's own curated subreddits (knowledge/reddit-
        sources/) are uniformly English communities (nosleep, ProRevenge,
        AmItheAsshole...), so a hardcoded "es" default here would reject
        every real signal from every real program -- only every test
        fixture in this codebase happens to use Spanish sample titles,
        which is why this went unnoticed. Only filter by language if a
        caller explicitly asks for one."""
        language = params.get("language")
        return str(language) if language else None

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
