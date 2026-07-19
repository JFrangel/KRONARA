import json
import os
import subprocess
import sys


def test_sidecar_cli_serves_authenticated_json_rpc():
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "handshake",
        "params": {"token": "secret", "protocol_version": 1},
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "kronara.sidecar",
            "--token",
            "secret",
            "--data-dir",
            ".test-tmp/sidecar-cli",
        ],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )

    response = json.loads(completed.stdout.strip())
    assert response["result"]["protocol_version"] == 1


def test_sidecar_extracts_safe_trend_signal_without_returning_body():
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "trend.extract",
            "params": {
                "source_id": "abc",
                "title": "A locked room changed my family",
                "body": "private authored story body",
                "score": 200,
                "comments": 50,
                "created_at": 100,
                "source_uri": "https://reddit.example/abc",
                "now": 200,
            },
        },
    ]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "kronara.sidecar",
            "--token",
            "secret",
            "--data-dir",
            ".test-tmp/sidecar-cli",
        ],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )

    response = json.loads(completed.stdout.splitlines()[1])
    assert response["result"]["source_id"] == "abc"
    assert "body" not in response["result"]
    assert "private authored" not in completed.stdout


def test_sidecar_exposes_agent_capabilities_without_arbitrary_execution():
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "agent.capabilities", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "agent.evaluate_narrative",
            "params": {
                "text": "Todo era un sueño.",
                "scores": {
                    "hook": 8,
                    "clarity": 8,
                    "conflict": 8,
                    "escalation": 8,
                    "agency": 8,
                    "coherence": 8,
                    "credibility": 8,
                    "originality": 8,
                    "retention": 8,
                    "payoff": 8,
                    "production_fit": 8,
                },
            },
        },
    ]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "kronara.sidecar",
            "--token",
            "secret",
            "--data-dir",
            ".test-tmp/sidecar-cli",
        ],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )

    capabilities = json.loads(completed.stdout.splitlines()[1])["result"]
    evaluation = json.loads(completed.stdout.splitlines()[2])["result"]
    assert "executive_orchestrator" in capabilities["agents"]
    assert "shell.execute" not in capabilities["tools"]
    assert evaluation["passed"] is False
    assert "dream_reset" in evaluation["antipatterns"]


def test_sidecar_exposes_operations_context_without_credentials():
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "operations.context", "params": {}},
    ]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "kronara.sidecar",
            "--token",
            "secret",
            "--data-dir",
            ".test-tmp/sidecar-cli",
        ],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )

    context = json.loads(completed.stdout.splitlines()[1])["result"]
    assert context["coverage"] == 1.0
    assert context["workflow_snapshot"]["publication_authority"] == "rust_only"
    assert "secret" not in json.dumps(context).casefold()
