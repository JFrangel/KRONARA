import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta


def test_virality_rpc_evaluates_platform_without_persistent_hidden_state():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    observations = []
    for index in range(24):
        signal = index / 23
        features = _features(
            vector_id=f"training-{index}",
            observed_at=start + timedelta(days=index),
            signal=signal,
        )
        observations.append(
            {
                "observation_id": f"observation-{index}",
                "features": features,
                "outcome_viral": int(index >= 12),
                "finalized_at": (start + timedelta(days=index, hours=72)).isoformat(),
            }
        )
    candidate = _features("candidate", start + timedelta(days=30), signal=0.85)
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
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "virality.evaluate",
                    "params": {"observations": observations, "candidate": candidate},
                },
            )
        )
        + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    response = json.loads(completed.stdout.splitlines()[1])

    assert response["result"]["forecast"]["status"] == "estimated"
    assert response["result"]["forecast"]["guaranteed"] is False
    assert response["result"]["model"]["platform_models"][0]["platform"] == "facebook_reels"


def _features(vector_id, observed_at, signal):
    return {
        "schema_version": 1,
        "vector_id": vector_id,
        "content_id": f"content-{vector_id}",
        "platform": "facebook_reels",
        "observed_at": observed_at.isoformat(),
        "age_hours": 12.0,
        "completion_rate": 0.25 + signal * 0.6,
        "share_rate": 0.01 + signal * 0.08,
        "replay_rate": 0.02 + signal * 0.12,
        "velocity_per_hour": 10 + signal * 990,
        "acceleration_per_hour2": -5 + signal * 30,
        "saturation_index": 0.3,
        "duration_seconds": 45.0,
    }
