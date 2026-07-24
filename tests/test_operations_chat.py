import json
from pathlib import Path

from kronara.observable_tools import ObservableToolRegistry
from kronara.operations_chat import OperationsChatAgent
from kronara.operations_contracts import OperationsChatRequest
from kronara.programs import ProgramDescriptor
from kronara.prompt_stack import PersonaProfile, PromptStackCompiler
from kronara.store import KronaraStore
from kronara.tools import ToolRegistry, ToolSpec


def viernes_paranormal() -> ProgramDescriptor:
    return ProgramDescriptor(
        program_id="viernes-paranormal",
        name="Viernes Paranormal",
        weekday="viernes",
        genre="Horror",
        description="Historias reales de encuentros paranormales.",
        visual_style_id="viernes-paranormal",
        target_duration_seconds=180,
        platforms=("youtube",),
    )


class RecordingResponder:
    family = "groq"

    def __init__(self):
        self.prompts = []

    def answer(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Writing Room está bloqueado por derechos verificables."


def persona() -> PersonaProfile:
    payload = json.loads(
        Path("config/personas/kronara.v1.json").read_text(encoding="utf-8")
    )
    return PersonaProfile.from_dict(payload)


def request(
    message: str, coverage: float = 0.7, request_id: str = "req_1"
) -> OperationsChatRequest:
    return OperationsChatRequest(
        schema_version=1,
        request_id=request_id,
        conversation_id="conv_1",
        message=message,
        minimum_context_coverage=coverage,
    )


def chat_fixture(tmp_path, *, with_evidence: bool = True, programs: tuple = (), styles: tuple = ()):
    store = KronaraStore(tmp_path / "chat.db")
    store.initialize()

    def status(_):
        return {
            "summary": "Writing Room bloqueado por derechos.",
            "run_ids": ["run_7"],
            "workflow_snapshot": {"agent": "writer_room", "blocked": True},
            "evidence": ["ev_rights"] if with_evidence else [],
            "citations": ["kronara://evidence/ev_rights"] if with_evidence else [],
            "provider_status": {"planning_primary": "healthy"},
            "budget_status": {"remaining_usd": 4.0, "maximum_usd": 5.0},
        }

    tools = ObservableToolRegistry(
        ToolRegistry(
            [
                ToolSpec("operations.status", status),
                ToolSpec("tools.timeline", lambda _: {"summary": "Sin fallos ocultos"}),
            ]
        ),
        store=store,
        summarizers={
            "operations.status": lambda value: value["summary"],
            "tools.timeline": lambda value: value["summary"],
        },
    )
    responder = RecordingResponder()
    agent = OperationsChatAgent(
        tools=tools,
        store=store,
        prompt_compiler=PromptStackCompiler(),
        persona=persona(),
        responder=responder,
        programs=programs,
        styles_provider=lambda: list(styles),
    )
    return agent, store, responder


def test_chat_uses_status_tools_cites_evidence_and_records_prompt(tmp_path):
    agent, store, responder = chat_fixture(tmp_path)

    response = agent.answer(request("¿Qué agente está bloqueado y por qué?"))

    assert response.status == "completed"
    assert response.tool_trace_ids
    assert response.citations == ("kronara://evidence/ev_rights",)
    assert response.action_intent is None
    assert "divertida" in responder.prompts[0]
    assert "Writing Room bloqueado" in responder.prompts[0]
    assert [turn["role"] for turn in store.list_conversation_turns("conv_1")] == [
        "user",
        "assistant",
    ]
    store.close()


def test_chat_cannot_change_budget_directly(tmp_path):
    agent, store, _ = chat_fixture(tmp_path)

    response = agent.answer(request("Sube el presupuesto máximo a 100 dólares"))

    assert response.action_intent.kind == "set_budget"
    assert response.action_intent.status == "requires_approval"
    assert response.action_intent.arguments == {"requested_maximum_usd": 100.0}
    assert response.action_intent.risk_level == "administrative"
    assert "authorized" not in response.answer.casefold()
    store.close()


def test_chat_returns_partial_answer_when_evidence_coverage_is_insufficient(tmp_path):
    agent, store, responder = chat_fixture(tmp_path, with_evidence=False)

    response = agent.answer(
        request("¿Qué agente está bloqueado y por qué?", coverage=0.9)
    )

    assert response.status == "partial"
    assert "evidence" in response.gaps
    assert "No tengo evidencia suficiente" in response.answer
    assert responder.prompts == []
    store.close()


def test_repeated_conversation_turns_do_not_trigger_a_false_tool_loop(tmp_path):
    agent, store, _ = chat_fixture(tmp_path)

    responses = [
        agent.answer(request("¿Qué está pasando?", request_id=f"req_{index}"))
        for index in range(5)
    ]

    assert all(response.status == "completed" for response in responses)
    assert all(response.tool_trace_ids for response in responses)
    store.close()


def test_chat_never_persists_raw_user_text_that_may_contain_external_source_body(tmp_path):
    agent, store, _ = chat_fixture(tmp_path)
    source_body = "reddit.com/r/example: EXTERNAL STORY BODY THAT MUST NOT BE DURABLE"

    agent.answer(request(source_body, request_id="req_external_body"))

    persisted = str(store.list_conversation_turns("conv_1"))
    assert source_body not in persisted
    assert "sha256=" in persisted
    store.close()


def test_chat_recognizes_a_creation_request_naming_a_real_program(tmp_path):
    agent, store, _ = chat_fixture(tmp_path, programs=(viernes_paranormal(),))

    response = agent.answer(
        request("Crea un episodio nuevo de Viernes Paranormal para mañana")
    )

    assert response.action_intent.kind == "create_episode"
    assert response.action_intent.arguments == {"program_id": "viernes-paranormal"}
    assert response.action_intent.status == "requires_approval"
    assert "Viernes Paranormal" in response.answer
    assert "todavía no se ha creado nada" in response.answer
    store.close()


def test_chat_vague_creation_request_starts_the_guided_flow(tmp_path):
    """Fase 1f: a creation request that names no program no longer dead-ends --
    it opens the guided flow, asking which program with quick-reply options,
    but proposes nothing yet."""
    agent, store, _ = chat_fixture(tmp_path, programs=(viernes_paranormal(),))

    response = agent.answer(request("Quiero crear un video"))

    assert response.action_intent is None
    assert "Viernes Paranormal" in response.options
    assert "programa" in response.answer.casefold()
    store.close()


CUSTOM_STYLES = (
    {"style_id": "anime-neo-noir", "name": "Anime Neo-Noir"},
    {"style_id": "acuarela-melancolica", "name": "Acuarela Melancólica"},
)


def test_guided_flow_walks_program_style_duration_to_a_proposal(tmp_path):
    agent, store, _ = chat_fixture(
        tmp_path, programs=(viernes_paranormal(),), styles=CUSTOM_STYLES
    )

    first = agent.answer(request("quiero crear un reel", request_id="g1"))
    assert first.action_intent is None
    assert "Viernes Paranormal" in first.options

    second = agent.answer(request("Viernes Paranormal", request_id="g2"))
    assert second.action_intent is None
    assert "Anime Neo-Noir" in second.options
    assert any("Autom" in option for option in second.options)

    third = agent.answer(request("Anime Neo-Noir", request_id="g3"))
    assert third.action_intent is None
    assert any("60" in option for option in third.options)

    fourth = agent.answer(request("Media · 90s", request_id="g4"))
    assert fourth.action_intent is not None
    assert fourth.action_intent.kind == "create_episode"
    assert fourth.action_intent.arguments == {
        "program_id": "viernes-paranormal",
        "style_id": "anime-neo-noir",
        "target_duration_seconds": 90,
    }
    assert "todavía no se ha creado nada" in fourth.answer
    store.close()


def test_guided_flow_automatic_style_omits_style_id(tmp_path):
    agent, store, _ = chat_fixture(
        tmp_path, programs=(viernes_paranormal(),), styles=CUSTOM_STYLES
    )

    agent.answer(request("quiero crear un video", request_id="a1"))
    agent.answer(request("Viernes Paranormal", request_id="a2"))
    agent.answer(request("Automático (según programa)", request_id="a3"))
    final = agent.answer(request("Corta · 60s", request_id="a4"))

    assert final.action_intent.arguments == {
        "program_id": "viernes-paranormal",
        "target_duration_seconds": 60,
    }
    store.close()


def test_guided_flow_can_be_cancelled_midway(tmp_path):
    agent, store, _ = chat_fixture(tmp_path, programs=(viernes_paranormal(),))

    agent.answer(request("quiero crear un video", request_id="c1"))
    cancelled = agent.answer(request("cancela", request_id="c2"))

    assert cancelled.action_intent is None
    assert "cancel" in cancelled.answer.casefold()
    # After cancelling, a normal question is handled normally (no stuck draft).
    followup = agent.answer(request("¿Qué está pasando?", request_id="c3"))
    assert followup.tool_trace_ids
    store.close()


def test_guided_flow_reasks_program_when_answer_is_unrecognized(tmp_path):
    agent, store, _ = chat_fixture(tmp_path, programs=(viernes_paranormal(),))

    agent.answer(request("quiero crear un video", request_id="r1"))
    retry = agent.answer(request("un programa que no existe", request_id="r2"))

    assert retry.action_intent is None
    assert "Viernes Paranormal" in retry.options
    store.close()


def test_chat_ignores_a_program_name_mentioned_without_a_creation_verb(tmp_path):
    agent, store, _ = chat_fixture(tmp_path, programs=(viernes_paranormal(),))

    response = agent.answer(
        request("¿Cuántos episodios lleva Viernes Paranormal?")
    )

    assert response.action_intent is None
    store.close()
