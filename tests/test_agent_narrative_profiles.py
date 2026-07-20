import json
from pathlib import Path

from kronara.agent_catalog import AgentCatalog
from kronara.prompt_stack import (
    AgentNarrativeProfile,
    PersonaProfile,
    PromptStackCompiler,
    PromptStackRequest,
)


def persona() -> PersonaProfile:
    return PersonaProfile(
        persona_id="kronara",
        version=1,
        traits=("analitica", "creativa"),
        rules=("Declara incertidumbre.",),
    )


def request(**overrides) -> PromptStackRequest:
    values = {
        "manifest_id": "prompt_ops_1",
        "version": 1,
        "core_policy": "No inventes tool calls.",
        "persona": persona(),
        "agent_role": "Explica la operación con evidencia.",
        "task_objective": "Responder qué trabajo está bloqueado.",
        "authority_budget": "Solo lectura; máximo 0.05 USD.",
        "context_packet": "run_1 está bloqueado por derechos.",
        "selected_skills": ("operations_chat",),
        "tool_contracts": ("operations.status",),
        "output_schema_id": "OperationsChatResponse@1",
        "verification": ("Cita cada afirmación operativa.",),
        "max_input_tokens": 1200,
        "narrative_profile": AgentNarrativeProfile(
            agent_id="operations_chat",
            version=1,
            tone="preciso y sereno",
            reasoning_style="separa hechos, inferencias e incertidumbre",
            communication_style="responde con contexto breve y citas",
            decision_style="elige opciones seguras y verificables",
            risk_posture="prioriza precisión sobre velocidad",
            response_shape="responde con contexto breve, citas y cierre claro",
            constraints=("no inventes herramientas", "no amplíes autoridad"),
            success_signals=("evidencia citada", "vacíos declarados"),
            closure_criteria=("deja explícito cuándo la respuesta está completa",),
        ),
    }
    values.update(overrides)
    return PromptStackRequest(**values)


def test_narrative_profile_is_included_in_compiled_prompt_stack():
    compiled = PromptStackCompiler().compile(request())

    assert "narrative_profile" in compiled.layer_ids
    assert "Tono" in compiled.text
    assert "preciso y sereno" in compiled.text
    assert "evidencia citada" in compiled.text


def test_agent_narrative_profile_can_be_loaded_from_config():
    payload = json.loads(
        Path("config/personas/operations_chat.v1.json").read_text(encoding="utf-8")
    )
    profile = AgentNarrativeProfile.from_dict(payload)

    assert profile.agent_id == "operations_chat"
    assert profile.version == 1
    assert profile.tone == "preciso y sereno"


def test_additional_agent_narrative_profiles_can_be_loaded_from_config():
    for agent_id in (
        "writer_room",
        "concept_architect",
        "research_executive",
        "context_engineer",
    ):
        payload = json.loads(
            Path(f"config/personas/{agent_id}.v1.json").read_text(encoding="utf-8")
        )
        profile = AgentNarrativeProfile.from_dict(payload)

        assert profile.agent_id == agent_id
        assert profile.version == 1
        assert profile.tone


def test_agent_catalog_can_resolve_narrative_profile_from_agent_configuration():
    catalog = AgentCatalog.load(Path("config/agents"))
    profile = AgentCatalog.load_narrative_profile(
        "operations_chat",
        Path("config/agents"),
        Path("config/personas"),
    )

    assert catalog.get("operations_chat")
    assert profile is not None
    assert profile.agent_id == "operations_chat"
    assert profile.version == 1


def test_agent_catalog_can_resolve_persona_and_narrative_profile_together():
    persona, narrative = AgentCatalog.load_runtime_profiles(
        "operations_chat",
        Path("config/agents"),
        Path("config/personas"),
    )

    assert persona is not None
    assert persona.persona_id == "kronara"
    assert narrative is not None
    assert narrative.agent_id == "operations_chat"


def test_prompt_request_builder_includes_narrative_profile_in_runtime_prompt():
    persona = PersonaProfile(
        persona_id="kronara",
        version=1,
        traits=("analitica",),
        rules=("Declara incertidumbre.",),
    )
    narrative = AgentNarrativeProfile(
        agent_id="operations_chat",
        version=1,
        tone="preciso y sereno",
        reasoning_style="separa hechos, inferencias e incertidumbre",
        communication_style="responde con contexto breve y citas",
        decision_style="elige opciones seguras y verificables",
        risk_posture="prioriza precisión sobre velocidad",
        response_shape="responde con contexto breve, citas y cierre claro",
        constraints=("no inventes herramientas",),
        success_signals=("evidencia citada",),
        closure_criteria=("deja claro cuándo la respuesta está completa",),
    )
    request = PromptStackRequest.from_runtime_profiles(
        manifest_id="runtime_prompt_1",
        version=1,
        core_policy="No inventes tool calls.",
        persona=persona,
        agent_role="Explica la operación.",
        task_objective="Responder con contexto.",
        authority_budget="Solo lectura.",
        context_packet="Contexto operativo.",
        selected_skills=("operations_chat",),
        tool_contracts=("operations.status",),
        output_schema_id="OperationsChatResponse@1",
        verification=("Cita evidencias.",),
        max_input_tokens=1200,
        narrative_profile=narrative,
    )
    compiled = PromptStackCompiler().compile(request)

    assert request.narrative_profile is narrative
    assert "Perfil narrativo del agente operations_chat" in compiled.text
    assert "preciso y sereno" in compiled.text
