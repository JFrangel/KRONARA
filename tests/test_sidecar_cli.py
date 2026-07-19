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
        [sys.executable, "-m", "kronara.sidecar", "--token", "secret"],
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
        [sys.executable, "-m", "kronara.sidecar", "--token", "secret"],
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
