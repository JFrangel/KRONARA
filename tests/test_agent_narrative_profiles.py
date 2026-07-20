import json
from pathlib import Path

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
            constraints=("no inventes herramientas", "no amplíes autoridad"),
            success_signals=("evidencia citada", "vacíos declarados"),
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
