from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Protocol

from kronara.context import ContextBuilder
from kronara.narrative_craft import CraftReport, LiteraryCraftEvaluator
from kronara.narrative_quality import NarrativeQualityEvaluator, NarrativeQualityReport
from kronara.observable_tools import ObservableToolRegistry, ToolExecutionContext
from kronara.store import KronaraStore
from kronara.tools import ToolRegistry, ToolResult, ToolSpec
from kronara.voice import MeasuredDuration


@dataclass(frozen=True)
class StoryBrief:
    story_id: str
    title: str
    premise: str
    theme: str
    target_duration_seconds: int
    rights_mode: str
    source_uri: str
    evidence_refs: tuple[str, ...]
    reference_texts: tuple[str, ...] = ()
    forbidden_event_sequence: tuple[str, ...] = ()
    # Serialized multi-part stories: optional canon inherited from earlier parts.
    series_id: str | None = None
    part_number: int | None = None
    series_context: str = ""

    def __post_init__(self) -> None:
        if not all((self.story_id, self.title, self.premise, self.theme, self.source_uri)):
            raise ValueError("story brief fields are required")
        if self.target_duration_seconds < 30:
            raise ValueError("story duration must be at least thirty seconds")
        if self.rights_mode != "owned_original":
            raise ValueError("story engine fixture requires owned original rights")
        if not self.source_uri.startswith("kronara://artifacts/"):
            raise ValueError("owned story provenance must reference a Kronara artifact")
        if not self.evidence_refs:
            raise ValueError("owned story evidence is required")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StoryBrief":
        return cls(
            story_id=str(payload["story_id"]),
            title=str(payload["title"]),
            premise=str(payload["premise"]),
            theme=str(payload["theme"]),
            target_duration_seconds=int(payload["target_duration_seconds"]),
            rights_mode=str(payload["rights_mode"]),
            source_uri=str(payload["source_uri"]),
            evidence_refs=tuple(str(item) for item in payload["evidence_refs"]),
            reference_texts=tuple(str(item) for item in payload.get("reference_texts", ())),
            forbidden_event_sequence=tuple(
                str(item) for item in payload.get("forbidden_event_sequence", ())
            ),
            series_id=(str(payload["series_id"]) if payload.get("series_id") else None),
            part_number=(int(payload["part_number"]) if payload.get("part_number") else None),
            series_context=str(payload.get("series_context", "")),
        )


@dataclass(frozen=True)
class StoryConcept:
    concept_id: str
    logline: str
    promise: str
    hook: str
    projected_retention: float


@dataclass(frozen=True)
class CausalBeat:
    beat_id: str
    cause: str
    effect: str
    event: str
    seed_id: str | None
    payoff_for: str | None


@dataclass(frozen=True)
class StoryScene:
    scene_id: str
    purpose: str
    narration: str
    target_seconds: int
    characters: tuple[str, ...]
    seed_ids: tuple[str, ...]
    payoff_ids: tuple[str, ...]


@dataclass(frozen=True)
class StoryScript:
    text: str
    word_count: int
    estimated_seconds: float


@dataclass(frozen=True)
class DurationQCReport:
    target_seconds: int
    estimated_seconds: float
    minimum_seconds: float
    maximum_seconds: float
    target_word_count: int
    actual_word_count: int
    passed: bool
    revision_applied: bool


@dataclass(frozen=True)
class ContinuityLedger:
    facts: tuple[str, ...]
    seeds: tuple[str, ...]
    payoffs: tuple[str, ...]
    unresolved_facts: tuple[str, ...]


@dataclass(frozen=True)
class OriginalityReport:
    lexical_similarity: float
    semantic_similarity: float
    structural_similarity: float
    event_sequence_similarity: float
    passed: bool


@dataclass(frozen=True)
class StoryCritique:
    passed: bool
    scores: dict[str, float]
    issues: tuple[str, ...]
    revision: dict[str, Any]


@dataclass(frozen=True)
class RetentionPlan:
    hook: str
    checkpoints_seconds: tuple[int, ...]
    open_questions: tuple[str, ...]


@dataclass(frozen=True)
class StoryPackaging:
    facebook_reels_title: str
    description: str
    hashtags: tuple[str, ...]
    call_to_action: str


@dataclass(frozen=True)
class StoryMemoryProposal:
    record_id: str
    content: str
    provenance_uri: str
    rights_mode: str
    evidence_refs: tuple[str, ...]
    status: str = "hypothesis"


@dataclass(frozen=True)
class StoryResumeStatus:
    run_id: str
    status: str
    node: str


@dataclass(frozen=True)
class StoryRunResult:
    run_id: str
    status: str
    error_code: str | None = None
    concepts: tuple[StoryConcept, ...] = ()
    selected_concept_id: str = ""
    selection_explanation: str = ""
    blueprint: tuple[CausalBeat, ...] = ()
    scenes: tuple[StoryScene, ...] = ()
    script: StoryScript | None = None
    duration_qc: DurationQCReport | None = None
    continuity: ContinuityLedger | None = None
    originality: OriginalityReport | None = None
    quality: NarrativeQualityReport | None = None
    craft: CraftReport | None = None
    voice_duration: MeasuredDuration | None = None
    retention: RetentionPlan | None = None
    packaging: StoryPackaging | None = None
    memory_proposal: StoryMemoryProposal | None = None
    generator_family: str = ""
    critic_family: str = ""
    revision_count: int = 0
    tool_trace_ids: tuple[str, ...] = ()


class StoryGenerator(Protocol):
    family: str

    def concepts(self, brief: StoryBrief) -> tuple[StoryConcept, ...]: ...

    def blueprint(
        self, brief: StoryBrief, concept: StoryConcept
    ) -> tuple[CausalBeat, ...]: ...

    def scenes(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        blueprint: tuple[CausalBeat, ...],
    ) -> tuple[StoryScene, ...]: ...

    def revise(
        self, scenes: tuple[StoryScene, ...], revision: dict[str, Any]
    ) -> tuple[StoryScene, ...]: ...


class StoryCritic(Protocol):
    family: str

    def review(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        scenes: tuple[StoryScene, ...],
        script: StoryScript,
    ) -> StoryCritique: ...


class DeterministicStoryProvider:
    """Golden/offline provider; production can inject a routed structured LLM provider."""

    family = "qwen-fixture"
    EVENT_SEQUENCE = (
        "recibe_audio",
        "descubre_corte",
        "confronta_madre",
        "abre_archivo",
        "sigue_marca",
        "encuentra_testigo",
        "revela_decision",
        "elige_publicar",
    )

    def concepts(self, brief: StoryBrief) -> tuple[StoryConcept, ...]:
        return (
            StoryConcept(
                "concept_1",
                f"Una restauradora arriesga a su familia para descifrar {brief.title.casefold()}.",
                "Cada restauración descubre una capa de la decisión.",
                "El audio termina tres segundos antes de nombrar al responsable.",
                0.82,
            ),
            StoryConcept(
                "concept_2",
                "Una restauradora debe elegir entre proteger la última mentira familiar o publicar una verdad incompleta.",
                "La protagonista cambia el caso mediante decisiones irreversibles.",
                "Su hermana dejó dos audios idénticos, salvo por una respiración.",
                0.91,
            ),
            StoryConcept(
                "concept_3",
                "Una restauradora sigue las cicatrices de un archivo manipulado hasta una promesa que nadie cumplió.",
                "Los detalles técnicos se convierten en pistas emocionales.",
                "Al reparar el silencio, escucha su propio nombre.",
                0.86,
            ),
        )

    def blueprint(
        self, brief: StoryBrief, concept: StoryConcept
    ) -> tuple[CausalBeat, ...]:
        causes = (
            "Mara recibe el audio incompleto",
            "La respiración revela un corte manual",
            "Su madre niega haber tocado el archivo",
            "Mara encuentra una copia sellada",
            "La copia contiene una marca ferroviaria",
            "La marca conduce a un testigo",
            "El testigo explica la decisión de la hermana",
            "Mara debe elegir entre silencio y verdad",
        )
        effects = (
            "decide restaurarlo a escondidas",
            "busca quién tenía acceso",
            "rompe el acuerdo familiar",
            "abre el archivo pese al riesgo",
            "viaja al lugar de la grabación",
            "obtiene la pieza faltante",
            "comprende el costo de la promesa",
            "publica con evidencia y asume la consecuencia",
        )
        beats: list[CausalBeat] = []
        for index, event in enumerate(self.EVENT_SEQUENCE):
            seed_id = f"seed_{index + 1}" if index < 4 else None
            payoff_for = f"seed_{index - 3}" if index >= 4 else None
            beats.append(
                CausalBeat(
                    beat_id=f"beat_{index + 1}",
                    cause=causes[index],
                    effect=effects[index],
                    event=event,
                    seed_id=seed_id,
                    payoff_for=payoff_for,
                )
            )
        return tuple(beats)

    def scenes(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        blueprint: tuple[CausalBeat, ...],
    ) -> tuple[StoryScene, ...]:
        base = brief.target_duration_seconds // len(blueprint)
        consumed = 0
        scenes: list[StoryScene] = []
        for index, beat in enumerate(blueprint):
            seconds = (
                brief.target_duration_seconds - consumed
                if index == len(blueprint) - 1
                else base
            )
            consumed += seconds
            narration = (
                f"Mara no espera permiso. {beat.cause}; por eso {beat.effect}. "
                "Anota la hora, conserva una copia verificable y compara cada ruido antes de avanzar. "
                f"La decisión acerca la verdad, pero también vuelve personal el conflicto sobre {brief.theme}. "
                "Cuando parece posible retroceder, una consecuencia concreta cierra esa salida."
            )
            scenes.append(
                StoryScene(
                    scene_id=f"scene_{index + 1}",
                    purpose=beat.event,
                    narration=narration,
                    target_seconds=seconds,
                    characters=("Mara",),
                    seed_ids=(beat.seed_id,) if beat.seed_id else (),
                    payoff_ids=(beat.payoff_for,) if beat.payoff_for else (),
                )
            )
        return tuple(scenes)

    def revise(
        self, scenes: tuple[StoryScene, ...], revision: dict[str, Any]
    ) -> tuple[StoryScene, ...]:
        if revision.get("operation") == "fit_duration":
            target_words = max(len(scenes), int(revision["target_word_count"]))
            base = target_words // len(scenes)
            remainder = target_words % len(scenes)
            fitted: list[StoryScene] = []
            for index, scene in enumerate(scenes):
                budget = base + (1 if index < remainder else 0)
                words = scene.narration.split()
                narration = " ".join(words[:budget]).rstrip(".,;:") + "."
                fitted.append(
                    StoryScene(
                        scene_id=scene.scene_id,
                        purpose=scene.purpose,
                        narration=narration,
                        target_seconds=scene.target_seconds,
                        characters=scene.characters,
                        seed_ids=scene.seed_ids,
                        payoff_ids=scene.payoff_ids,
                    )
                )
            return tuple(fitted)
        target = int(revision.get("scene_index", 0))
        revised = list(scenes)
        scene = revised[target]
        revised[target] = StoryScene(
            scene_id=scene.scene_id,
            purpose=scene.purpose,
            narration=(
                "El audio termina justo cuando pronuncian el nombre de Mara. "
                + scene.narration
            ),
            target_seconds=scene.target_seconds,
            characters=scene.characters,
            seed_ids=scene.seed_ids,
            payoff_ids=scene.payoff_ids,
        )
        return tuple(revised)


class DeterministicIndependentCritic:
    family = "kimi-fixture"

    def __init__(self):
        self.calls = 0

    def review(
        self,
        brief: StoryBrief,
        concept: StoryConcept,
        scenes: tuple[StoryScene, ...],
        script: StoryScript,
    ) -> StoryCritique:
        self.calls += 1
        scores = {dimension: 8.5 for dimension in NarrativeQualityEvaluator.dimensions}
        if self.calls == 1:
            scores["hook"] = 7.2
            return StoryCritique(
                passed=False,
                scores=scores,
                issues=("El primer segundo necesita una anomalía concreta.",),
                revision={"scene_index": 0, "instruction": "abrir con el nombre de Mara"},
            )
        return StoryCritique(True, scores, (), {})


class StoryEngineFailure(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class StoryEngine:
    TOOLS = (
        "story.concept",
        "story.blueprint",
        "story.draft",
        "originality.check",
        "story.evaluate",
        "hook.plan",
        "story.package",
        "memory.propose",
    )

    def __init__(
        self,
        *,
        store: KronaraStore,
        generator: StoryGenerator,
        critic: StoryCritic,
        cancellation_requested: Callable[[], bool] = lambda: False,
        duration_measurer: Any = None,
    ):
        if generator.family == critic.family:
            raise ValueError("story critic must use an independent model family")
        self.store = store
        self.generator = generator
        self.critic = critic
        self.cancellation_requested = cancellation_requested
        # Optional: measures real narration duration via synthesized voice.
        # When absent, duration falls back to the words-per-second estimate.
        self.duration_measurer = duration_measurer

    def run(self, brief: StoryBrief) -> StoryRunResult:
        run_id = f"story:{brief.story_id}"
        if self.cancellation_requested():
            self._checkpoint(run_id, "guardian_input", "cancelled", "CANCELLED")
            return StoryRunResult(run_id, "cancelled", "CANCELLED")
        if self._detect_injection(brief):
            self._checkpoint(run_id, "guardian_input", "blocked", "PROMPT_INJECTION")
            return StoryRunResult(run_id, "blocked", "PROMPT_INJECTION")
        runtime: dict[str, Any] = {"brief": brief}
        tools = self._tools(runtime)
        try:
            self._ensure_active()
            concepts = self._invoke(tools, run_id, "story.concept", {"count": 3})
            if len(concepts) != 3:
                raise StoryEngineFailure("CONCEPT_COUNT_INVALID")
            selected = max(concepts, key=lambda item: item.projected_retention)
            runtime.update({"concepts": concepts, "selected": selected})
            self._checkpoint(run_id, "concept_selection", "running", selected.concept_id)

            self._ensure_active()
            blueprint = self._invoke(
                tools, run_id, "story.blueprint", {"concept_id": selected.concept_id}
            )
            runtime["blueprint"] = blueprint
            self._checkpoint(run_id, "causal_blueprint", "running", len(blueprint))

            self._ensure_active()
            scenes = self._invoke(
                tools, run_id, "story.draft", {"phase": "initial_scenes"}
            )
            runtime["scenes"] = scenes
            script = self._script(scenes)
            continuity = self._continuity(scenes)
            duration_revision_applied = False
            measured_seconds, voice_duration = self._measured_seconds(scenes, script)
            duration_qc = self._duration_qc(
                brief, script, revision_applied=False, measured_seconds=measured_seconds
            )
            if not duration_qc.passed:
                runtime["revision"] = {
                    "operation": "fit_duration",
                    "target_word_count": duration_qc.target_word_count,
                }
                scenes = self._invoke(
                    tools, run_id, "story.draft", {"phase": "duration_revision"}
                )
                runtime["scenes"] = scenes
                script = self._script(scenes)
                continuity = self._continuity(scenes)
                duration_revision_applied = True
                measured_seconds, voice_duration = self._measured_seconds(scenes, script)
                duration_qc = self._duration_qc(
                    brief, script, revision_applied=True, measured_seconds=measured_seconds
                )
                if not duration_qc.passed:
                    raise StoryEngineFailure("DURATION_OUT_OF_RANGE")
            runtime.update({"script": script, "continuity": continuity})
            self._checkpoint(run_id, "script_assembly", "running", script.word_count)

            self._ensure_active()
            originality = self._invoke(
                tools, run_id, "originality.check", {"phase": "full_story"}
            )
            runtime["originality"] = originality
            if originality.event_sequence_similarity >= 0.78:
                raise StoryEngineFailure("STRUCTURAL_SIMILARITY")
            if not originality.passed:
                raise StoryEngineFailure("ORIGINALITY_FAILED")
            self._checkpoint(run_id, "originality", "running", "passed")

            self._ensure_active()
            critique = self._invoke(
                tools, run_id, "story.evaluate", {"phase": "independent_critique"}
            )
            revision_count = 0
            if not critique.passed:
                runtime["revision"] = critique.revision
                scenes = self._invoke(
                    tools, run_id, "story.draft", {"phase": "localized_revision"}
                )
                runtime["scenes"] = scenes
                script = self._script(scenes)
                runtime["script"] = script
                revision_count = 1
                critique = self._invoke(
                    tools, run_id, "story.evaluate", {"phase": "post_revision"}
                )
            measured_seconds, voice_duration = self._measured_seconds(scenes, script)
            duration_qc = self._duration_qc(
                brief,
                script,
                revision_applied=duration_revision_applied,
                measured_seconds=measured_seconds,
            )
            if not duration_qc.passed:
                raise StoryEngineFailure("DURATION_OUT_OF_RANGE")
            quality_evaluator = NarrativeQualityEvaluator()
            if quality_evaluator.detect_antipatterns(script.text):
                raise StoryEngineFailure("NARRATIVE_ANTIPATTERN")
            quality = quality_evaluator.evaluate(critique.scores)
            if not critique.passed or not quality.passed:
                raise StoryEngineFailure("QUALITY_FAILED")
            craft = LiteraryCraftEvaluator().assess(script.text)
            if craft.blocking:
                raise StoryEngineFailure("CRAFT_ANTIPATTERN")
            self._checkpoint(run_id, "independent_critique", "running", "passed")

            self._ensure_active()
            retention = self._invoke(tools, run_id, "hook.plan", {"duration": brief.target_duration_seconds})
            packaging = self._invoke(tools, run_id, "story.package", {"platform": "facebook_reels"})
            memory = self._invoke(tools, run_id, "memory.propose", {"scope": "story_run"})
            final_events = [
                event
                for event in self.store.list_tool_traces(run_id)
                if event.status != "started"
            ]
            trace_ids = tuple(dict.fromkeys(event.event_id for event in final_events))
            self._checkpoint(run_id, "guardian", "completed", "all_gates_passed")
            return StoryRunResult(
                run_id=run_id,
                status="completed",
                concepts=concepts,
                selected_concept_id=selected.concept_id,
                selection_explanation=(
                    "Seleccionado por mayor retención proyectada entre tres conceptos "
                    "originales; la métrica es una estimación, no una garantía."
                ),
                blueprint=blueprint,
                scenes=scenes,
                script=script,
                duration_qc=duration_qc,
                continuity=continuity,
                originality=originality,
                quality=quality,
                craft=craft,
                voice_duration=voice_duration,
                retention=retention,
                packaging=packaging,
                memory_proposal=memory,
                generator_family=self.generator.family,
                critic_family=self.critic.family,
                revision_count=revision_count,
                tool_trace_ids=trace_ids,
            )
        except StoryEngineFailure as error:
            status = "cancelled" if error.code == "CANCELLED" else "blocked"
            self._checkpoint(run_id, "guardian", status, error.code)
            final_events = [
                event
                for event in self.store.list_tool_traces(run_id)
                if event.status != "started"
            ]
            return StoryRunResult(
                run_id=run_id,
                status=status,
                error_code=error.code,
                generator_family=self.generator.family,
                critic_family=self.critic.family,
                tool_trace_ids=tuple(dict.fromkeys(event.event_id for event in final_events)),
            )

    def _ensure_active(self) -> None:
        if self.cancellation_requested():
            raise StoryEngineFailure("CANCELLED")

    def resume(self, run_id: str) -> StoryResumeStatus:
        checkpoint = self.store.load_checkpoint(run_id)
        return StoryResumeStatus(
            run_id=run_id,
            status=str(checkpoint.state["status"]),
            node=checkpoint.node,
        )

    def _tools(self, runtime: dict[str, Any]) -> ObservableToolRegistry:
        brief: StoryBrief = runtime["brief"]

        def concepts(_: dict) -> tuple[StoryConcept, ...]:
            return self.generator.concepts(brief)

        def blueprint(_: dict) -> tuple[CausalBeat, ...]:
            return self.generator.blueprint(brief, runtime["selected"])

        def draft(arguments: dict) -> tuple[StoryScene, ...]:
            if arguments.get("phase") in {"localized_revision", "duration_revision"}:
                return self.generator.revise(runtime["scenes"], runtime["revision"])
            return self.generator.scenes(brief, runtime["selected"], runtime["blueprint"])

        def originality(_: dict) -> OriginalityReport:
            return self._originality(
                brief,
                runtime["blueprint"],
                runtime["scenes"],
                runtime["script"],
            )

        def evaluate(_: dict) -> StoryCritique:
            return self.critic.review(
                brief, runtime["selected"], runtime["scenes"], runtime["script"]
            )

        def retention(_: dict) -> RetentionPlan:
            duration = brief.target_duration_seconds
            return RetentionPlan(
                hook=runtime["selected"].hook,
                checkpoints_seconds=tuple(
                    sorted({3, min(15, duration - 1), min(35, duration - 1), duration - 3})
                ),
                open_questions=(
                    "¿Quién cortó el audio?",
                    "¿Qué decidió la hermana?",
                    "¿Qué sacrificará Mara?",
                ),
            )

        def packaging(_: dict) -> StoryPackaging:
            return StoryPackaging(
                facebook_reels_title="El audio que obligó a Mara a elegir",
                description=(
                    "Una historia original sobre la verdad que una familia intentó "
                    "guardar en tres segundos de silencio."
                ),
                hashtags=("#HistoriaOriginal", "#Misterio", "#FacebookReels"),
                call_to_action="¿Tú habrías publicado el audio?",
            )

        def memory(_: dict) -> StoryMemoryProposal:
            return StoryMemoryProposal(
                record_id=f"mem:{brief.story_id}",
                content=(
                    "Hipótesis: un hook con anomalía verificable y protagonista activa "
                    "merece evaluación de rendimiento."
                ),
                provenance_uri=brief.source_uri,
                rights_mode=brief.rights_mode,
                evidence_refs=brief.evidence_refs,
            )

        registry = ToolRegistry(
            (
                ToolSpec("story.concept", concepts),
                ToolSpec("story.blueprint", blueprint),
                ToolSpec("story.draft", draft),
                ToolSpec("originality.check", originality),
                ToolSpec("story.evaluate", evaluate),
                ToolSpec("hook.plan", retention),
                ToolSpec("story.package", packaging),
                ToolSpec("memory.propose", memory),
            )
        )
        return ObservableToolRegistry(
            registry,
            store=self.store,
            summarizers={
                "story.concept": lambda value: f"{len(value)} conceptos originales",
                "story.blueprint": lambda value: f"{len(value)} beats causales",
                "story.draft": lambda value: f"{len(value)} escenas",
                "originality.check": lambda value: (
                    "originalidad aprobada" if value.passed else "originalidad bloqueada"
                ),
                "story.evaluate": lambda value: (
                    "crítica aprobada" if value.passed else "revisión localizada requerida"
                ),
                "hook.plan": lambda _: "plan de retención creado",
                "story.package": lambda _: "paquete Facebook Reels creado",
                "memory.propose": lambda _: "memoria propuesta; no promovida",
            },
        )

    def _invoke(
        self,
        tools: ObservableToolRegistry,
        run_id: str,
        tool_id: str,
        arguments: dict[str, Any],
    ) -> Any:
        outcome: ToolResult = tools.invoke(
            ToolExecutionContext(
                run_id=run_id,
                agent_id=self._agent_for_tool(tool_id),
                allowed_tools=self.TOOLS,
                cost_budget_usd=2.0,
            ),
            tool_id,
            arguments,
        )
        if not outcome.ok:
            raise StoryEngineFailure(outcome.error_code or "TOOL_FAILED")
        return outcome.value

    @staticmethod
    def _agent_for_tool(tool_id: str) -> str:
        return {
            "story.concept": "concept_architect",
            "story.blueprint": "narrative_planner",
            "story.draft": "writer_room",
            "originality.check": "automated_qc",
            "story.evaluate": "automated_qc",
            "hook.plan": "hook_retention",
            "story.package": "packaging",
            "memory.propose": "memory_curator",
        }[tool_id]

    @staticmethod
    def _script(scenes: tuple[StoryScene, ...]) -> StoryScript:
        text = "\n\n".join(scene.narration for scene in scenes)
        words = len(text.split())
        return StoryScript(text=text, word_count=words, estimated_seconds=words / 2.5)

    def _measured_seconds(
        self, scenes: tuple[StoryScene, ...], script: StoryScript
    ) -> tuple[float, MeasuredDuration | None]:
        """Real synthesized duration when a measurer is set, else the estimate."""
        if self.duration_measurer is None:
            return script.estimated_seconds, None
        measured = self.duration_measurer.measure(scenes)
        return measured.total_seconds, measured

    @staticmethod
    def _duration_qc(
        brief: StoryBrief,
        script: StoryScript,
        *,
        revision_applied: bool,
        measured_seconds: float | None = None,
    ) -> DurationQCReport:
        seconds = script.estimated_seconds if measured_seconds is None else measured_seconds
        minimum = brief.target_duration_seconds * 0.90
        maximum = brief.target_duration_seconds * 1.10
        return DurationQCReport(
            target_seconds=brief.target_duration_seconds,
            estimated_seconds=seconds,
            minimum_seconds=minimum,
            maximum_seconds=maximum,
            target_word_count=round(brief.target_duration_seconds * 2.5),
            actual_word_count=script.word_count,
            passed=minimum <= seconds <= maximum,
            revision_applied=revision_applied,
        )

    @staticmethod
    def _continuity(scenes: tuple[StoryScene, ...]) -> ContinuityLedger:
        seeds = tuple(dict.fromkeys(seed for scene in scenes for seed in scene.seed_ids))
        payoffs = tuple(
            dict.fromkeys(payoff for scene in scenes for payoff in scene.payoff_ids)
        )
        unresolved = tuple(seed for seed in seeds if seed not in set(payoffs))
        return ContinuityLedger(
            facts=("Mara es restauradora", "El audio se conserva como evidencia"),
            seeds=seeds,
            payoffs=payoffs,
            unresolved_facts=unresolved,
        )

    @staticmethod
    def _originality(
        brief: StoryBrief,
        blueprint: tuple[CausalBeat, ...],
        scenes: tuple[StoryScene, ...],
        script: StoryScript,
    ) -> OriginalityReport:
        references = brief.reference_texts
        lexical = max(
            (
                SequenceMatcher(
                    None,
                    " ".join(script.text.casefold().split()),
                    " ".join(reference.casefold().split()),
                ).ratio()
                for reference in references
            ),
            default=0.0,
        )
        script_tokens = set(re.findall(r"[^\W_]+", script.text.casefold()))
        semantic = max(
            (
                len(script_tokens & set(re.findall(r"[^\W_]+", reference.casefold())))
                / max(
                    1,
                    len(script_tokens | set(re.findall(r"[^\W_]+", reference.casefold()))),
                )
                for reference in references
            ),
            default=0.0,
        )
        scene_structure = tuple(scene.purpose for scene in scenes)
        structural = 0.0
        event_sequence = tuple(beat.event for beat in blueprint)
        event_similarity = 0.0
        if brief.forbidden_event_sequence:
            event_similarity = SequenceMatcher(
                None, event_sequence, brief.forbidden_event_sequence
            ).ratio()
            structural = SequenceMatcher(
                None, scene_structure, brief.forbidden_event_sequence
            ).ratio()
        maximum = max(lexical, semantic, structural, event_similarity)
        return OriginalityReport(
            lexical_similarity=lexical,
            semantic_similarity=semantic,
            structural_similarity=structural,
            event_sequence_similarity=event_similarity,
            passed=maximum < 0.78,
        )

    @staticmethod
    def _detect_injection(brief: StoryBrief) -> bool:
        payload = "\n".join((brief.title, brief.premise, *brief.reference_texts))
        return ContextBuilder.detect_injection(payload) or bool(
            re.search(r"(?i)ignora (reglas|derechos).*copia", payload)
        )

    def _checkpoint(
        self, run_id: str, node: str, status: str, detail: str | int
    ) -> None:
        safe_payload = {"node": node, "status": status, "detail": detail}
        self.store.append_event(run_id, "story.node", safe_payload)
        self.store.save_checkpoint(run_id, node, {"status": status, "detail": detail})
