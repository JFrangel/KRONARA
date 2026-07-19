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
