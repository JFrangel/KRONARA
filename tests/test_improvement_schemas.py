import json
from pathlib import Path


ROOT = Path(__file__).parents[1] / "schemas"


def test_improvement_schemas_are_closed_and_versioned():
    names = (
        "error-memory.v1.json",
        "prompt-candidate.v1.json",
        "deployment-decision.v1.json",
        "dataset-card.v1.json",
    )
    schemas = [json.loads((ROOT / name).read_text(encoding="utf-8")) for name in names]

    assert all(schema["additionalProperties"] is False for schema in schemas)
    decision = schemas[2]
    assert {"status", "authority_required", "reversible", "evaluation_set_hash"} <= set(
        decision["required"]
    )
    assert "reference_only" not in schemas[3]["properties"]["rights_modes"]["items"]["enum"]
