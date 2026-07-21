from __future__ import annotations

import threading
from pathlib import Path

from kronara.operations_service import OperationsService
from kronara.rpc import JsonRpcServer


def _request(method: str, params: dict, request_id: int = 2) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }


def _server(tmp_path: Path) -> tuple[JsonRpcServer, OperationsService]:
    service = OperationsService(tmp_path / "runtime")
    server = JsonRpcServer(token="secret", methods=service.methods())
    handshake = server.handle(
        _request(
            "handshake",
            {"token": "secret", "protocol_version": 1},
            request_id=1,
        )
    )
    assert handshake["result"]["protocol_version"] == 1
    return server, service


def test_resolve_program_defaults_fills_subreddits_and_duration_from_the_program():
    """The UI's "create an episode for program X" action only needs to send
    program_id -- subreddits and target_duration_seconds are derived the
    same way the autonomous scheduler already derives them for its own
    weekly runs (see autonomous_loop.py's _fire())."""
    resolved = OperationsService._resolve_program_defaults(
        {"program_id": "viernes-paranormal", "story_id": "owned_manual_1"}
    )

    assert resolved["subreddits"]
    assert all(isinstance(item, str) for item in resolved["subreddits"])
    assert resolved["target_duration_seconds"] > 0
    assert resolved["sort"] == "hot"
    assert resolved["story_id"] == "owned_manual_1"


def test_resolve_program_defaults_never_overrides_explicit_subreddits():
    """Estudio's free-text manual test path already supplies its own
    subreddits -- program_id auto-fill must never override a caller who
    already knows exactly what it wants."""
    resolved = OperationsService._resolve_program_defaults(
        {"program_id": "viernes-paranormal", "subreddits": ["Historias"]}
    )

    assert resolved["subreddits"] == ["Historias"]


def test_resolve_program_defaults_is_a_no_op_without_a_program_id():
    params = {"subreddits": ["Historias"], "target_duration_seconds": 60}

    assert OperationsService._resolve_program_defaults(params) == params


def test_operations_chat_is_authenticated_and_returns_visible_trace_ids(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(
        _request(
            "operations.chat",
            {
                "schema_version": 1,
                "request_id": "chat_1",
                "conversation_id": "operations_1",
                "message": "¿Qué está pasando en la operación?",
            },
        )
    )

    assert response["result"]["schema_version"] == 1
    assert response["result"]["status"] == "completed"
    assert response["result"]["tool_trace_ids"]
    assert response["result"]["citations"]
    service.close()


def test_programs_list_returns_all_seven_programs_with_visual_style_linkage(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(_request("programs.list", {}))

    programs = response["result"]["programs"]
    assert len(programs) == 7
    viernes = next(p for p in programs if p["program_id"] == "viernes-paranormal")
    assert viernes["weekday"] == "viernes"
    assert viernes["visual_style_id"] == "viernes-paranormal"
    assert "youtube" in viernes["platforms"]
    service.close()


def test_episodes_list_returns_most_recent_first(tmp_path):
    server, service = _server(tmp_path)
    service.store.save_owned_story_artifact(
        story_id="ep_old", artifact_uri="kronara://sha256/a", path="/a", sha256="a",
        created_at=100, program_id="viernes-paranormal",
        metadata={"title": "La casa vieja", "duration_seconds": 95.0, "generator_family": "qwen-routed"},
    )
    service.store.save_owned_story_artifact(
        story_id="ep_new", artifact_uri="kronara://sha256/b", path="/b", sha256="b",
        created_at=200, program_id="cronicas-de-justicia",
        metadata={"title": "El expediente", "duration_seconds": 110.0},
    )

    response = server.handle(_request("episodes.list", {}))

    episodes = response["result"]["episodes"]
    assert [item["story_id"] for item in episodes] == ["ep_new", "ep_old"]
    assert episodes[1]["title"] == "La casa vieja"
    assert episodes[1]["program_id"] == "viernes-paranormal"
    assert episodes[1]["generator_family"] == "qwen-routed"
    service.close()


def test_episodes_list_respects_limit_param(tmp_path):
    server, service = _server(tmp_path)
    for i in range(3):
        service.store.save_owned_story_artifact(
            story_id=f"ep_{i}", artifact_uri=f"kronara://sha256/{i}", path=f"/{i}", sha256=str(i),
            created_at=i, metadata={"title": f"Episodio {i}"},
        )

    response = server.handle(_request("episodes.list", {"limit": 2}))

    assert len(response["result"]["episodes"]) == 2
    service.close()


def test_story_test_exposes_progress_and_completed_tool_timeline(tmp_path):
    server, service = _server(tmp_path)

    story = server.handle(_request("story.test", {"wait": False}))
    run_id = story["result"]["run_id"]
    service._threads[run_id].join(timeout=5)
    progress = server.handle(_request("run.progress", {"run_id": run_id}, 3))
    timeline = server.handle(_request("tools.timeline", {"run_id": run_id}, 4))

    assert story["result"]["status"] in {"queued", "running", "completed"}
    assert progress["result"]["status"] == "completed"
    assert progress["result"]["progress_percent"] == 100
    assert progress["result"]["concept_count"] == 3
    assert any(event["tool_id"] == "story.concept" for event in timeline["result"]["events"])
    assert all("arguments_redacted" in event for event in timeline["result"]["events"])
    service.close()


def test_story_test_rejects_synchronous_execution_that_cannot_be_cancelled(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(_request("story.test", {"wait": True}))

    assert response["error"]["code"] == -32602
    assert "synchronous" in response["error"]["message"]
    service.close()


def test_cancel_is_idempotent_and_never_claims_an_external_effect(tmp_path):
    server, service = _server(tmp_path)

    first = server.handle(_request("run.cancel", {"run_id": "run_1"}))
    second = server.handle(_request("run.cancel", {"run_id": "run_1"}, 3))

    assert first["result"] == second["result"]
    assert first["result"]["status"] == "cancelled"
    assert first["result"]["external_effect"] is False
    service.close()


def test_context_memory_and_rag_methods_return_bounded_structured_results(tmp_path):
    server, service = _server(tmp_path)

    context = server.handle(_request("operations.context", {}, 3))["result"]
    memories = server.handle(
        _request("memory.search", {"scope": "operations", "limit": 5}, 4)
    )["result"]
    retrieval = server.handle(
        _request(
            "rag.retrieve_v3",
            {"query": "¿Cómo protege Kronara los derechos?", "limit": 3},
            5,
        )
    )["result"]

    assert context["schema_version"] == 1
    assert context["coverage"] == 1.0
    assert len(memories["records"]) <= 5
    assert len(retrieval["results"]) <= 3
    assert retrieval["index_id"].startswith("ragv3:")
    service.close()


def test_rust_control_snapshot_is_reflected_in_operations_context(tmp_path):
    server, service = _server(tmp_path)

    synced = server.handle(
        _request("operations.control_snapshot", {"paused": True}, 3)
    )["result"]
    context = server.handle(_request("operations.context", {}, 4))["result"]

    assert synced["paused"] is True
    assert context["workflow_snapshot"]["paused"] is True
    service.close()


def test_paused_control_blocks_new_story_runs_and_cancels_active_runs(tmp_path):
    server, service = _server(tmp_path)
    active_run_id = "story:active"
    service._states[active_run_id] = service._run_state(active_run_id, "running", 25, "draft")
    service._cancellations[active_run_id] = threading.Event()

    server.handle(_request("operations.control_snapshot", {"paused": True}, 3))
    blocked = server.handle(_request("story.test", {"wait": False}, 4))["result"]

    assert service._cancellations[active_run_id].is_set()
    assert blocked["status"] == "blocked"
    assert blocked["error_code"] == "GLOBAL_PAUSE"
    service.close()


def test_schedule_tick_with_no_prior_history_finds_every_program_due(tmp_path, monkeypatch):
    """A fresh install has no schedule_last_fired rows, so every program's
    "next occurrence since epoch 0" is deep in the past relative to any real
    `now` -- B1's grid should immediately try all 7 on its very first tick
    rather than silently waiting a full week for each. With no real
    authority configured (OperationsService(tmp_path) defaults to
    UnavailableAuthorityClient), reddit.list_signals fails immediately and
    content_pipeline.py's real no-credential fallback kicks in -- which
    means it would otherwise make 7 real, unthrottled RSS calls to Reddit
    per test run. Stub it out: this test is about the scheduler reaching
    every due program safely, not about live Reddit availability/rate
    limits (those are covered by test_content_pipeline_vertical.py's
    dedicated, mocked-transport RSS fallback tests)."""
    from kronara.reddit_rss import RedditRssReader

    monkeypatch.setattr(RedditRssReader, "trending", lambda self, *a, **k: [])
    server, service = _server(tmp_path)

    response = server.handle(_request("schedule.tick", {"now": 1_784_930_400}))

    result = response["result"]
    assert result["checked_at"] == 1_784_930_400
    assert len(result["outcomes"]) == 7
    assert all(outcome["status"] == "failed" for outcome in result["outcomes"])
    assert result["ran"] == []
    service.close()


def test_schedule_tick_at_the_very_start_of_time_has_nothing_due_yet(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(_request("schedule.tick", {"now": 0}))

    assert response["result"]["outcomes"] == []
    service.close()


def test_schedule_tick_respects_global_pause(tmp_path):
    server, service = _server(tmp_path)
    server.handle(_request("operations.control_snapshot", {"paused": True}, 3))

    response = server.handle(_request("schedule.tick", {"now": 1_784_930_400}, 4))

    assert response["result"]["outcomes"] == []
    service.close()
