import json
from pathlib import Path


ROOT = Path(__file__).parents[1] / "schemas"


def test_virality_contract_schemas_are_closed_and_forbid_guarantees():
    vector = json.loads(
        (ROOT / "platform-feature-vector.v1.json").read_text(encoding="utf-8")
    )
    forecast = json.loads(
        (ROOT / "virality-forecast.v1.json").read_text(encoding="utf-8")
    )

    assert vector["additionalProperties"] is False
    assert forecast["additionalProperties"] is False
    assert {"velocity_per_hour", "acceleration_per_hour2", "saturation_index", "age_hours"} <= set(
        vector["required"]
    )
    assert forecast["properties"]["guaranteed"]["const"] is False
    assert {"probability", "interval", "unknown_factors", "explanation"} <= set(
        forecast["required"]
    )
