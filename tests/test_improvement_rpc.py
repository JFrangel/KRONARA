import json
import os
import subprocess
import sys


def test_improvement_rpc_exposes_policy_and_requires_approval_for_prompts():
    candidate = {
        "version_id": "prompt-v2",
        "parameter": "system_prompt",
        "config_hash": "hash-prompt-v2",
        "created_at": "2026-07-18T00:00:00+00:00",
        "expires_at": "2026-08-18T00:00:00+00:00",
    }
    completed = subprocess.run(
        [sys.executable, "-m", "kronara.sidecar", "--token", "secret"],
        input="\n".join(
            json.dumps(request)
            for request in (
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "handshake",
                    "params": {"token": "secret", "protocol_version": 1},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "improvement.status", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "improvement.evaluate",
                    "params": {
                        "champion": {**candidate, "version_id": "prompt-v1"},
                        "challenger": candidate,
                        "evaluation": {
                            "evaluation_id": "evaluation-1",
                            "evaluation_set": {
                                "set_id": "golden-1",
                                "version": 1,
                                "frozen": True,
                                "content_hash": "golden-hash",
                                "case_count": 100,
                            },
                            "sample_size": 500,
                            "champion_score": 0.5,
                            "challenger_score": 0.6,
                            "safety_regressions": [],
                            "cost_change_ratio": 0.05,
                            "platform_stability": 0.95,
                        },
                        "as_of": "2026-07-19T00:00:00+00:00",
                    },
                },
            )
        )
        + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]

    assert "voice_id" in responses[1]["result"]["automatic_parameters"]
    assert "rights_policy" in responses[1]["result"]["administrative_parameters"]
    assert responses[2]["result"]["status"] == "requires_approval"
    assert responses[2]["result"]["authority_required"] == "supervised"
