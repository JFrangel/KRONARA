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


def test_authenticated_rpc_executes_only_registered_analytics():
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
                "method": "analytics.execute",
                "params": {
                    "operation": "describe",
                    "inputs": {"values": [1, 2, None, 3]},
                    "unit": "seconds",
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "analytics.execute",
                "params": {"operation": "run_python", "inputs": {}},
            },
        ]
    )

    assert responses[1]["result"]["result"]["mean"] == 2.0
    assert responses[1]["result"]["unit"] == "seconds"
    assert responses[2]["error"]["code"] == -32602
