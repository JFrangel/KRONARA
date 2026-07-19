import json
from pathlib import Path


ROOT = Path(__file__).parents[1] / "schemas"


def test_performance_contract_schemas_are_closed_and_versioned():
    snapshot = json.loads((ROOT / "metric-snapshot.v1.json").read_text(encoding="utf-8"))
    diagnosis = json.loads(
        (ROOT / "performance-diagnosis.v1.json").read_text(encoding="utf-8")
    )

    assert snapshot["additionalProperties"] is False
    assert diagnosis["additionalProperties"] is False
    assert {"voice_id", "topic", "hook_id", "publication_hour", "audience_segment"} <= set(
        snapshot["required"]
    )
    assert {"segments", "hypotheses", "warnings", "input_hash"} <= set(
        diagnosis["required"]
    )
