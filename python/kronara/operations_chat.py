from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from kronara.observable_tools import ObservableToolRegistry, ToolExecutionContext
from kronara.operations_contracts import (
    ActionIntent,
    OperationsChatRequest,
    OperationsChatResponse,
    OperationsContextPacket,
)
from kronara.programs import ProgramDescriptor
from kronara.prompt_stack import (
    AgentNarrativeProfile,
    PersonaProfile,
    PromptStackCompiler,
    PromptStackRequest,
)
from kronara.store import KronaraStore


class OperationsResponder(Protocol):
    family: str

    def answer(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class ChatIntent:
    kind: str
    tools: tuple[str, ...]
    action_kind: str | None = None
    action_arguments: dict[str, Any] | None = None


class OperationsContextBuilder:
    REQUIRED_TOPICS = ("workflow", "tool_trace", "evidence")

    def build(
        self,
        *,
        packet_id: str,
        tool_values: dict[str, dict[str, Any]],
        tool_trace_ids: tuple[str, ...],
    ) -> OperationsContextPacket:
        status = tool_values.get("operations.status", {})
        workflow = dict(status.get("workflow_snapshot", {}))
        evidence = tuple(str(item) for item in status.get("evidence", ()))
        present = {
            "workflow": bool(workflow),
            "tool_trace": bool(tool_trace_ids),
            "evidence": bool(evidence),
        }
        missing = tuple(topic for topic in self.REQUIRED_TOPICS if not present[topic])
        coverage = sum(present.values()) / len(self.REQUIRED_TOPICS)
        return OperationsContextPacket(
            schema_version=1,
            packet_id=packet_id,
            run_ids=tuple(str(item) for item in status.get("run_ids", ())),
            workflow_snapshot=workflow,
            tool_trace_ids=tool_trace_ids,
            evidence_refs=evidence,
            citations=tuple(str(item) for item in status.get("citations", ())),
            memory_record_ids=tuple(
                str(item) for item in status.get("memory_record_ids", ())
            ),
            provider_status={
                str(key): str(value)
                for key, value in dict(status.get("provider_status", {})).items()
            },
            budget_status={
                str(key): float(value)
                for key, value in dict(status.get("budget_status", {})).items()
            },
            coverage=coverage,
            missing_topics=missing,
        )


class OperationsChatAgent:
    ALLOWED_TOOLS = (
        "operations.status",
        "tools.timeline",
        "evidence.read",
        "metrics.read",
        "performance.diagnose",
        "memory.search",
    )

    # Deliberately regex-based, not LLM-classified -- the same "no inventes
    # tool calls" policy this agent's own prompt stack enforces on the
    # responder applies to itself: an action_intent must be a deterministic,
    # auditable function of the literal text, never a guess.
    CREATION_VERB_PATTERN = re.compile(
        r"\b(crea|crear|creame|cr[eé]ame|genera|generar|produce|producir|arma|armame|quiero|hacer|haz)\b"
    )
    # A creation verb alone ("genera un resumen") isn't enough to start the
    # guided video flow -- it must also name a content noun so we don't hijack
    # unrelated requests.
    CONTENT_NOUN_PATTERN = re.compile(
        r"\b(video|v[ií]deo|reel|historia|episodio|contenido|corto|clip)\b"
    )
    CANCEL_PATTERN = re.compile(r"\b(cancela|cancelar|cancelalo|olv[ií]dalo|d[eé]jalo|detente|mejor no)\b")

    def __init__(
        self,
        *,
        tools: ObservableToolRegistry,
        store: KronaraStore,
        prompt_compiler: PromptStackCompiler,
        persona: PersonaProfile,
        responder: OperationsResponder,
        narrative_profile: AgentNarrativeProfile | None = None,
        context_builder: OperationsContextBuilder | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        programs: tuple[ProgramDescriptor, ...] = (),
        styles_provider: Callable[[], list[dict[str, Any]]] | None = None,
    ):
        self.tools = tools
        self.store = store
        self.prompt_compiler = prompt_compiler
        self.persona = persona
        self.responder = responder
        self.narrative_profile = narrative_profile
        self.context_builder = context_builder or OperationsContextBuilder()
        self.clock = clock
        self._programs = programs
        self._program_by_id = {program.program_id: program for program in programs}
        # Fase 1f guided creation: lists the visual styles for the "estilo"
        # question; defaults to none so the flow still works (style stays
        # automatic) when no provider is wired.
        self._styles_provider = styles_provider or (lambda: [])
        # Per-conversation slot-filling state for the guided flow. In-memory:
        # a guided creation spans a few turns within one session.
        self._creation_drafts: dict[str, dict[str, Any]] = {}

    def answer(self, request: OperationsChatRequest) -> OperationsChatResponse:
        # Fase 1f: the guided creation flow is deterministic and cheap -- it
        # runs before the tool/context machinery and returns early when it owns
        # the turn (an active draft, or a fresh "quiero crear un video").
        guided = self._guided_creation(request)
        if guided is not None:
            self._save_turns(request, guided)
            return guided
        intent = self._classify(request.message)
        run_id = f"chat:{request.request_id}"
        tool_values: dict[str, dict[str, Any]] = {}
        for tool_id in intent.tools:
            outcome = self.tools.invoke(
                ToolExecutionContext(
                    run_id=run_id,
                    agent_id="operations_chat",
                    allowed_tools=self.ALLOWED_TOOLS,
                    cost_budget_usd=0.05,
                ),
                tool_id,
                {
                    "conversation_id": request.conversation_id,
                    "request_id": request.request_id,
                },
            )
            if outcome.ok and isinstance(outcome.value, dict):
                tool_values[tool_id] = dict(outcome.value)
        final_traces = [
            event
            for event in self.store.list_tool_traces(run_id)
            if event.status != "started"
        ]
        trace_ids = tuple(dict.fromkeys(event.event_id for event in final_traces))
        packet = self.context_builder.build(
            packet_id=f"ctx:{request.request_id}",
            tool_values=tool_values,
            tool_trace_ids=trace_ids,
        )
        action_intent = self._action_intent(request, intent)
        if packet.coverage < request.minimum_context_coverage:
            response = OperationsChatResponse(
                schema_version=1,
                request_id=request.request_id,
                status="partial",
                answer=(
                    "No tengo evidencia suficiente para afirmarlo con seguridad. "
                    f"Falta: {', '.join(packet.missing_topics)}."
                ),
                citations=packet.citations,
                tool_trace_ids=packet.tool_trace_ids,
                gaps=packet.missing_topics,
                action_intent=action_intent,
            )
        elif action_intent is not None:
            response = OperationsChatResponse(
                schema_version=1,
                request_id=request.request_id,
                status="completed",
                answer=self._confirmation_text(intent, action_intent),
                citations=packet.citations,
                tool_trace_ids=packet.tool_trace_ids,
                gaps=(),
                action_intent=action_intent,
            )
        else:
            compiled = self.prompt_compiler.compile(
                self._prompt_request(request, packet, tool_values)
            )
            answer = self.responder.answer(compiled.text).strip()
            response = OperationsChatResponse(
                schema_version=1,
                request_id=request.request_id,
                status="completed",
                answer=answer or "La herramienta respondió sin un resumen utilizable.",
                citations=packet.citations,
                tool_trace_ids=packet.tool_trace_ids,
                gaps=(),
                action_intent=None,
            )
        self._save_turns(request, response)
        return response

    def _save_turns(
        self, request: OperationsChatRequest, response: OperationsChatResponse
    ) -> None:
        now = self.clock()
        self.store.save_conversation_turn(
            conversation_id=request.conversation_id,
            role="user",
            content=self._durable_turn_summary("user", request.message),
            created_at=now,
        )
        self.store.save_conversation_turn(
            conversation_id=request.conversation_id,
            role="assistant",
            content=self._durable_turn_summary("assistant", response.answer),
            created_at=now,
        )

    @staticmethod
    def _durable_turn_summary(role: str, content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return f"[{role} turn omitted from durable memory; sha256={digest}; chars={len(content)}]"

    def _classify(self, message: str) -> ChatIntent:
        normalized = message.casefold()
        budget_match = re.search(
            r"(?:presupuesto|budget)[^0-9]{0,40}([0-9]+(?:[.,][0-9]+)?)",
            normalized,
        )
        if budget_match:
            amount = float(budget_match.group(1).replace(",", "."))
            return ChatIntent(
                kind="administrative_action",
                tools=("operations.status",),
                action_kind="set_budget",
                action_arguments={"requested_maximum_usd": amount},
            )
        if self.CREATION_VERB_PATTERN.search(normalized):
            program = self._match_program(normalized)
            if program is not None:
                return ChatIntent(
                    kind="administrative_action",
                    tools=("operations.status",),
                    action_kind="create_episode",
                    action_arguments={"program_id": program.program_id},
                )
        return ChatIntent(
            kind="operation_status",
            tools=("operations.status", "tools.timeline"),
        )

    def _match_program(self, normalized_message: str) -> ProgramDescriptor | None:
        """Only ever matches a program whose real configured name literally
        appears in the message -- never a fuzzy or LLM-guessed match, so an
        approved action can't silently target a program the user didn't
        name."""
        for program in self._programs:
            if program.name.casefold() in normalized_message:
                return program
        return None

    # ---- Guided creation flow (Fase 1f) -------------------------------------

    def _guided_creation(
        self, request: OperationsChatRequest
    ) -> OperationsChatResponse | None:
        """Slot-filling state machine: programa → estilo → duración → propuesta.
        Owns the turn only when a draft is active for this conversation, or when
        the message is a *vague* creation request ("quiero crear un video") that
        names no program. A creation request that already names a program keeps
        the existing one-shot fast path (see _classify)."""
        conv = request.conversation_id
        normalized = request.message.casefold()
        draft = self._creation_drafts.get(conv)

        if draft is None:
            starts = bool(
                self.CREATION_VERB_PATTERN.search(normalized)
                and self.CONTENT_NOUN_PATTERN.search(normalized)
            )
            if not starts or self._match_program(normalized) is not None:
                return None  # not a vague creation request -> let _classify decide
            self._creation_drafts[conv] = {"step": "program"}
            return self._ask_program(request)

        if self.CANCEL_PATTERN.search(normalized):
            self._creation_drafts.pop(conv, None)
            return self._plain(
                request, "Listo, cancelé la creación guiada. ¿En qué más te ayudo?"
            )

        step = draft["step"]
        if step == "program":
            program = self._match_program(normalized)
            if program is None:
                return self._ask_program(request, retry=True)
            draft["program_id"] = program.program_id
            draft["step"] = "style"
            return self._ask_style(request)
        if step == "style":
            draft["style_id"] = self._match_style(normalized)
            draft["step"] = "duration"
            return self._ask_style_confirmed_ask_duration(request, draft)
        if step == "duration":
            draft["target_duration_seconds"] = self._match_duration(normalized)
            self._creation_drafts.pop(conv, None)
            return self._propose_creation(request, draft)
        # Unknown step -> reset defensively.
        self._creation_drafts.pop(conv, None)
        return None

    def _ask_program(
        self, request: OperationsChatRequest, *, retry: bool = False
    ) -> OperationsChatResponse:
        names = [program.name for program in self._programs]
        text = (
            "No reconocí ese programa. ¿Para cuál de estos quieres el video?"
            if retry
            else "¡Perfecto! Vamos a crear un video. ¿Para qué programa?"
        )
        return self._options_response(request, text, names)

    def _ask_style(self, request: OperationsChatRequest) -> OperationsChatResponse:
        options = ["Automático (según programa)"] + [
            str(style.get("name", style.get("style_id", "")))
            for style in self._styles_provider()
        ]
        return self._options_response(
            request, "¿Qué estilo visual prefieres para este video?", options
        )

    def _ask_style_confirmed_ask_duration(
        self, request: OperationsChatRequest, draft: dict[str, Any]
    ) -> OperationsChatResponse:
        return self._options_response(
            request,
            "Anotado. ¿Qué duración quieres?",
            ["Corta · 60s", "Media · 90s", "Larga · 180s"],
        )

    def _propose_creation(
        self, request: OperationsChatRequest, draft: dict[str, Any]
    ) -> OperationsChatResponse:
        arguments: dict[str, Any] = {"program_id": draft["program_id"]}
        if draft.get("style_id"):
            arguments["style_id"] = draft["style_id"]
        if draft.get("target_duration_seconds"):
            arguments["target_duration_seconds"] = draft["target_duration_seconds"]
        intent = ChatIntent(
            kind="administrative_action",
            tools=(),
            action_kind="create_episode",
            action_arguments=arguments,
        )
        action_intent = self._action_intent(request, intent)
        program = self._program_by_id.get(draft["program_id"])
        name = program.name if program is not None else draft["program_id"]
        style_label = draft.get("style_id") or "automático (según programa)"
        seconds = draft.get("target_duration_seconds") or (
            program.target_duration_seconds if program is not None else 90
        )
        answer = (
            f'Listo para crear un episodio de "{name}" · estilo {style_label} · '
            f"{seconds}s. Apruébalo para ejecutarlo; todavía no se ha creado nada."
        )
        return OperationsChatResponse(
            schema_version=1,
            request_id=request.request_id,
            status="completed",
            answer=answer,
            citations=(),
            tool_trace_ids=(),
            gaps=(),
            action_intent=action_intent,
        )

    def _match_style(self, normalized_message: str) -> str:
        """Map a free-text / chip answer to a style_id. 'automático'/'auto' (or
        anything unrecognized) -> '' so the program's configured style decides."""
        if "auto" in normalized_message:
            return ""
        for style in self._styles_provider():
            style_id = str(style.get("style_id", ""))
            name = str(style.get("name", "")).casefold()
            if (name and name in normalized_message) or (
                style_id and style_id.casefold() in normalized_message
            ):
                return style_id
        return ""

    @staticmethod
    def _match_duration(normalized_message: str) -> int:
        """Map an answer to seconds. Explicit digits win; else the qualitative
        labels corta/media/larga; else 90s (the standard reel length)."""
        digits = re.search(r"(\d{2,4})", normalized_message)
        if digits:
            return max(30, min(600, int(digits.group(1))))
        if "corta" in normalized_message or "corto" in normalized_message:
            return 60
        if "larga" in normalized_message or "largo" in normalized_message:
            return 180
        return 90

    def _plain(
        self, request: OperationsChatRequest, text: str
    ) -> OperationsChatResponse:
        return OperationsChatResponse(
            schema_version=1,
            request_id=request.request_id,
            status="completed",
            answer=text,
            citations=(),
            tool_trace_ids=(),
            gaps=(),
            action_intent=None,
        )

    def _options_response(
        self, request: OperationsChatRequest, text: str, options: list[str]
    ) -> OperationsChatResponse:
        return OperationsChatResponse(
            schema_version=1,
            request_id=request.request_id,
            status="completed",
            answer=text,
            citations=(),
            tool_trace_ids=(),
            gaps=(),
            action_intent=None,
            options=tuple(dict.fromkeys(option for option in options if option)),
        )

    def _confirmation_text(self, intent: ChatIntent, action_intent: ActionIntent) -> str:
        if intent.action_kind == "create_episode":
            program_id = str(action_intent.arguments.get("program_id", ""))
            program = self._program_by_id.get(program_id)
            name = program.name if program is not None else program_id
            return (
                f'Preparé la creación de un episodio nuevo de "{name}". '
                "Apruébala para ejecutarla; todavía no se ha creado nada."
            )
        return (
            "Preparé una propuesta administrativa, pero no está autorizada ni "
            "ha cambiado la operación. Rust debe validarla y pedir confirmación."
        )

    @staticmethod
    def _action_intent(
        request: OperationsChatRequest, intent: ChatIntent
    ) -> ActionIntent | None:
        if intent.action_kind is None:
            return None
        arguments = dict(intent.action_arguments or {})
        normalized = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(
            f"{request.conversation_id}:{intent.action_kind}:{normalized}".encode()
        ).hexdigest()[:20]
        return ActionIntent(
            schema_version=1,
            intent_id=f"intent_{digest}",
            kind=intent.action_kind,
            arguments=arguments,
            risk_level="administrative",
            status="requires_approval",
            idempotency_key=f"{request.conversation_id}:{digest}",
        )

    def _prompt_request(
        self,
        request: OperationsChatRequest,
        packet: OperationsContextPacket,
        tool_values: dict[str, dict[str, Any]],
    ) -> PromptStackRequest:
        context = json.dumps(
            {
                "packet": {
                    "workflow_snapshot": packet.workflow_snapshot,
                    "citations": packet.citations,
                    "provider_status": packet.provider_status,
                    "budget_status": packet.budget_status,
                },
                "tool_results": tool_values,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return PromptStackRequest.from_runtime_profiles(
            manifest_id=f"operations:{request.request_id}",
            version=1,
            core_policy=(
                "No inventes tool calls. No amplíes autoridad. Separa hechos, "
                "inferencias e incertidumbre y cita la evidencia disponible."
            ),
            persona=self.persona,
            agent_role="Explica la operación de Kronara con precisión y claridad.",
            task_objective=request.message,
            authority_budget="Solo lectura; máximo 0.05 USD; los cambios son intents.",
            context_packet=context,
            selected_skills=(
                "operations_chat",
                "context_engineering",
                "tool_trace_explanation",
            ),
            tool_contracts=tuple(tool_values) or ("operations.status",),
            output_schema_id="OperationsChatResponse@1",
            verification=(
                "Cita afirmaciones operativas.",
                "Declara vacíos y fallos de herramientas.",
                "No afirmes que una propuesta ya fue autorizada.",
            ),
            max_input_tokens=8000,
            narrative_profile=self.narrative_profile,
        )
