import json
import os
import subprocess
import sys


def call_sidecar(requests):
    completed = subprocess.run(
        [sys.executable, "-m", "kronara.sidecar", "--token", "secret"],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    return [json.loads(line) for line in completed.stdout.splitlines()]


def test_research_rpc_plans_and_evaluates_normalized_evidence():
    question = {
        "question_id": "rpc-research",
        "question": "¿Qué voz ofrece mejor retención?",
        "language": "es",
        "max_cost_usd": 2.0,
        "max_sources": 6,
    }
    responses = call_sidecar(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "handshake",
                "params": {"token": "secret", "protocol_version": 1},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "research.plan",
                "params": question,
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "research.evaluate",
                "params": {
                    "question": question,
                    "records": [
                        {
                            "record_id": "metric-1",
                            "source_uri": "kronara://metrics/metric-1",
                            "publisher": "kronara",
                            "source_family": "first-party-facebook",
                            "published_at": "2026-07-18T00:00:00+00:00",
                            "retrieved_at": "2026-07-19T00:00:00+00:00",
                            "valid_until": "2026-08-19T00:00:00+00:00",
                            "rights_mode": "owned_original",
                            "assertions": [
                                {
                                    "claim_id": "sample-size",
                                    "subquestion_id": "rpc-research:measurement",
                                    "text": "La muestra contiene 120 publicaciones.",
                                    "kind": "fact",
                                    "stance": "support",
                                    "confidence": 0.95,
                                }
                            ],
                        },
                        {
                            "record_id": "metric-2",
                            "source_uri": "kronara://metrics/metric-2",
                            "publisher": "kronara-audit",
                            "source_family": "first-party-audit",
                            "published_at": "2026-07-18T00:00:00+00:00",
                            "retrieved_at": "2026-07-19T00:00:00+00:00",
                            "valid_until": "2026-08-19T00:00:00+00:00",
                            "rights_mode": "owned_original",
                            "assertions": [
                                {
                                    "claim_id": "sample-size",
                                    "subquestion_id": "rpc-research:measurement",
                                    "text": "La muestra contiene 120 publicaciones.",
                                    "kind": "fact",
                                    "stance": "support",
                                    "confidence": 0.9,
                                }
                            ],
                        },
                    ],
                },
            },
        ]
    )

    assert responses[1]["result"]["intent"] == "comparative"
    assert responses[1]["result"]["subquestions"][0]["focus"] == "measurement"
    assert responses[2]["result"]["brief"]["facts"] == [
        "La muestra contiene 120 publicaciones."
    ]
    assert responses[2]["result"]["brief"]["status"] == "partial"
