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
        r"\b(crea|crear|creame|cr[eé]ame|genera|generar|produce|producir|arma|armame)\b"
    )

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

    def answer(self, request: OperationsChatRequest) -> OperationsChatResponse:
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
        return response

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
