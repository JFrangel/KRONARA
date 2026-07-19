import json
from pathlib import Path


SCHEMAS = (
    "operations-chat-request.v1.json",
    "operations-chat-response.v1.json",
    "action-intent.v1.json",
    "operations-context-packet.v1.json",
    "memory-record.v2.json",
    "tool-trace-event.v1.json",
    "tool-trace-summary.v1.json",
    "reddit-signal-query.v1.json",
    "reddit-signal-page.v1.json",
    "embedding-model-descriptor.v1.json",
    "embedding-evaluation.v1.json",
    "retrieval-query.v3.json",
    "retrieval-evaluation.v2.json",
    "owned-story-performance.v1.json",
    "story-reuse-decision.v1.json",
    "prompt-stack-manifest.v1.json",
    "persona-profile.v1.json",
)


def test_v04_boundary_schemas_exist_are_closed_and_versioned():
    root = Path("schemas")
    for filename in SCHEMAS:
        payload = json.loads((root / filename).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["type"] == "object"
        assert payload["additionalProperties"] is False
        assert "schema_version" in payload["properties"]
        assert "schema_version" in payload["required"]

