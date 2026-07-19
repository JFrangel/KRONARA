import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta


def test_performance_rpc_returns_reproducible_non_causal_diagnosis():
    published = datetime(2026, 7, 19, 12, tzinfo=UTC)
    snapshots = []
    for voice, completions in (("voice-a", 60), ("voice-b", 40)):
        for index in range(3):
            snapshots.append(
                {
                    "schema_version": 1,
                    "snapshot_id": f"{voice}-{index}",
                    "content_id": f"content-{voice}-{index}",
                    "platform": "facebook_reels",
                    "published_at": (published + timedelta(minutes=index)).isoformat(),
                    "observed_at": (published + timedelta(hours=48)).isoformat(),
                    "metric_window_hours": 48,
                    "impressions": 200,
                    "starts": 100,
                    "completions": completions,
                    "replays": 10,
                    "shares": 5,
                    "watch_time_seconds": 2475.0,
                    "duration_seconds": 45.0,
                    "voice_id": voice,
                    "topic": "suspenso",
                    "hook_id": "confesion",
                    "publication_hour": 12,
                    "audience_segment": "broad",
                }
            )
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
                    "method": "performance.diagnose",
                    "params": {"snapshots": snapshots},
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

    assert response["result"]["platform"] == "facebook_reels"
    assert response["result"]["status"] == "ready_for_experiment"
    assert response["result"]["hypotheses"][0]["causal_claim"] is False
    assert "observational_not_causal" in response["result"]["warnings"]
    assert len(response["result"]["input_hash"]) == 64
