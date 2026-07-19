import json
from pathlib import Path

from kronara.agent_catalog import AgentCatalog


def test_required_agent_manifests_are_valid_and_tools_are_known():
    root = Path(__file__).parents[1]
    catalog = AgentCatalog.load(root / "config" / "agents")

    required = {
        "executive_orchestrator",
        "opportunity_intelligence",
        "rights_provenance",
        "concept_architect",
        "narrative_planner",
        "writer_room",
        "automated_qc",
        "performance_scientist",
        "memory_curator",
        "research_executive",
        "evidence_analyst",
    }
    assert required <= set(catalog.agent_ids)
    assert catalog.unknown_tools() == ()
    assert catalog.get("writer_room").model_family != catalog.get("automated_qc").model_family
    assert catalog.get("research_executive").model_family != catalog.get("evidence_analyst").model_family

    skills = json.loads(
        (root / "config" / "skills" / "catalog.v1.json").read_text(encoding="utf-8")
    )
    registered = {item["skill_id"] for item in skills["skills"]}
    used = {skill for agent_id in catalog.agent_ids for skill in catalog.get(agent_id).skills}
    assert used <= registered
