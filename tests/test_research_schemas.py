import json
from pathlib import Path


SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def load(name):
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def test_research_boundary_schemas_are_closed_and_versioned():
    plan = load("research-plan.v1.json")
    source = load("source-record.v1.json")
    evidence = load("evidence-matrix.v1.json")
    brief = load("analytical-brief.v1.json")

    for schema in (plan, source, evidence, brief):
        assert schema["additionalProperties"] is False
        assert schema["$id"].endswith(".json")

    assert {"schema_version", "question_id", "intent", "risk", "subquestions", "stopping_rule"} <= set(
        plan["required"]
    )
    assert source["properties"]["assertions"]["items"]["additionalProperties"] is False
    assert {"claims", "contradictions", "coverage", "dependent_source_groups"} <= set(
        evidence["required"]
    )
    assert {"status", "coverage", "contradictions", "warnings"} <= set(brief["required"])
