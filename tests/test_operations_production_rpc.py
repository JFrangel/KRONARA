from datetime import UTC, datetime, timedelta

from kronara.artifacts import ArtifactStore
from kronara.operations_service import OperationsService


NOW = datetime(2026, 7, 19, 18, tzinfo=UTC)


class FakeMetaAuthority:
    def __init__(self):
        self.calls = []

    def invoke(self, tool_id, arguments):
        self.calls.append((tool_id, arguments))
        if tool_id == "meta.metrics.read":
            return {
                "schema_version": 1,
                "remote_id": arguments["remote_id"],
                "observed_at": int(NOW.timestamp()),
                "metrics": {
                    "plays": 300,
                    "completions": 250,
                    "average_watch_time_ms": 72_000,
                    "reach": 400,
                    "shares": 40,
                },
                "evidence_ref": "meta://metrics/remote-win/evidence-1",
            }
        raise AssertionError(tool_id)


def cohort(content_id, completions, *, voice="voice-a", hook="hook-a"):
    return {
        "schema_version": 1,
        "snapshot_id": f"metric-{content_id}",
        "content_id": content_id,
        "platform": "facebook",
        "published_at": (NOW - timedelta(hours=72)).isoformat(),
        "observed_at": NOW.isoformat(),
        "metric_window_hours": 72,
        "impressions": 400,
        "starts": 300,
        "completions": completions,
        "replays": 20,
        "shares": 10,
        "watch_time_seconds": 15_000,
        "duration_seconds": 90,
        "voice_id": voice,
        "topic": "misterio familiar",
        "hook_id": hook,
        "publication_hour": 18,
        "audience_segment": "latam-general",
    }


def test_operations_service_exposes_content_and_meta_learning_vertical(tmp_path):
    authority = FakeMetaAuthority()
    service = OperationsService(tmp_path / "runtime", authority=authority)
    artifact = ArtifactStore(tmp_path / "artifacts").put_bytes(
        "Historia propia de una restauradora y una respiración imposible.".encode("utf-8")
    )
    story_id = "owned-meta-winner"
    service.store.save_owned_story_artifact(
        story_id=story_id,
        artifact_uri=f"kronara://sha256/{artifact.sha256}",
        path=str(artifact.path),
        sha256=artifact.sha256,
        metadata={
            "rights_mode": "owned_original",
            "narrative_passed": True,
            "originality_passed": True,
            "safety_passed": True,
            "golden_no_regression": True,
        },
    )

    result = service.performance_learn(
        {
            "story_id": story_id,
            "remote_id": "remote-win",
            "published_at": (NOW - timedelta(hours=72)).isoformat(),
            "duration_seconds": 90,
            "voice_id": "voice-winner",
            "topic": "misterio familiar",
            "hook_id": "hook-winner",
            "publication_hour": 18,
            "audience_segment": "latam-general",
            "cohort_snapshots": [
                cohort("winner-variant", 240, voice="voice-winner", hook="hook-winner"),
                cohort("baseline-1", 150),
                cohort("baseline-2", 145),
            ],
        }
    )

    assert "content.run" in service.methods()
    assert "performance.learn" in service.methods()
    assert result["decision"]["status"] == "promoted_rag_example"
    assert result["diagnosis"]["status"] == "ready_for_experiment"
    assert len(service.store.list_metric_snapshots("facebook")) == 4
    assert authority.calls == [("meta.metrics.read", {"remote_id": "remote-win"})]
    retrieval = service.rag_retrieve(
        {"query": "restauradora respiración", "limit": 5, "now": 1_900_000_000}
    )
    assert story_id in {item["document_id"] for item in retrieval["results"]}
    service.close()
