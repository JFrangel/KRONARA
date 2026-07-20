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
