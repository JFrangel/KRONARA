from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from kronara.operations_contracts import ToolTraceEvent
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


def test_styles_list_returns_the_ten_shipped_styles(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(_request("styles.list", {}))

    styles = response["result"]["styles"]
    ids = {s["style_id"] for s in styles}
    assert {"anime-neo-noir", "analog-horror-vhs", "editorial-minimalista"} <= ids
    assert all(s["source"] == "base" for s in styles)
    service.close()


def test_styles_upsert_then_list_shows_custom_style(tmp_path):
    server, service = _server(tmp_path)

    saved = server.handle(
        _request(
            "styles.upsert",
            {
                "style_id": "mi-estilo",
                "name": "Mi Estilo",
                "style_prompt": "custom look, dreamy pastel gradients",
                "motion_bias": "subtle",
            },
        )
    )
    assert saved["result"]["status"] == "saved"

    listed = server.handle(_request("styles.list", {}))
    by_id = {s["style_id"]: s for s in listed["result"]["styles"]}
    assert by_id["mi-estilo"]["source"] == "custom"
    assert by_id["mi-estilo"]["name"] == "Mi Estilo"
    service.close()


def test_styles_upsert_rejects_invalid_style(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(
        _request("styles.upsert", {"style_id": "x", "name": "X", "motion_bias": "bad"})
    )
    # style_prompt missing AND motion_bias invalid -> JSON-RPC error, not a save.
    assert "error" in response
    service.close()


def test_styles_delete_reverts_override_to_base(tmp_path):
    server, service = _server(tmp_path)

    server.handle(
        _request(
            "styles.upsert",
            {
                "style_id": "anime-neo-noir",
                "name": "Editado",
                "style_prompt": "my own edited anime look",
            },
        )
    )
    assert any(
        s["style_id"] == "anime-neo-noir" and s["source"] == "custom-override"
        for s in server.handle(_request("styles.list", {}))["result"]["styles"]
    )

    deleted = server.handle(_request("styles.delete", {"style_id": "anime-neo-noir"}))
    assert deleted["result"]["status"] == "deleted"
    assert any(
        s["style_id"] == "anime-neo-noir" and s["source"] == "base"
        for s in deleted["result"]["styles"]
    )
    service.close()


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
    # v0.8: programs link to one of the 10 named visual styles (styles.v1.json)
    # rather than a self-referential program_id. Viernes Paranormal -> horror.
    assert viernes["visual_style_id"] == "analog-horror-vhs"
    assert "youtube" in viernes["platforms"]
    assert viernes["narrative_template"]
    assert viernes["narrative_template_source"] == "base"
    assert "La Casa que Respiraba" in viernes["story_resource_text"]
    assert "La Niña del Espejo" in viernes["story_resource_text"]
    assert viernes["story_resource_source"] == "base"
    assert any(item["title"] == "La Casa que Respiraba" for item in viernes["story_resource_items"])
    assert any(item["title"] == "La Niña del Espejo" for item in viernes["story_resource_items"])
    service.close()


def test_program_template_can_be_saved_and_restored_from_local_ui(tmp_path):
    server, service = _server(tmp_path)

    saved = server.handle(_request("programs.template.save", {
        "program_id": "viernes-paranormal",
        "directives": [
            "Terror paranormal claro.",
            "Entidad visible antes del cierre.",
            "Residuo final inquietante.",
        ],
    }))

    assert saved["result"]["status"] == "saved"
    response = server.handle(_request("programs.list", {}))
    viernes = next(p for p in response["result"]["programs"] if p["program_id"] == "viernes-paranormal")
    assert viernes["narrative_template_source"] == "manual"
    assert viernes["narrative_template"][1] == "Entidad visible antes del cierre."

    reset = server.handle(_request("programs.template.reset", {"program_id": "viernes-paranormal"}))
    assert reset["result"]["status"] == "reset"
    response = server.handle(_request("programs.list", {}))
    viernes = next(p for p in response["result"]["programs"] if p["program_id"] == "viernes-paranormal")
    assert viernes["narrative_template_source"] == "base"
    service.close()


def test_program_story_resources_can_be_saved_restored_and_retrieved_by_rag(tmp_path):
    server, service = _server(tmp_path)

    custom_text = """### 1. Historia Larga - "La Escalera que Susurraba"

Una familia llega a una casa vieja y descubre que la escalera susurra nombres
distintos cada madrugada. La hija menor empieza a responderle, el padre graba
audio, la vecina reconoce la voz de un inquilino muerto y la sombra termina
subiendo los escalones hacia el cuarto principal.
"""
    saved = server.handle(_request("programs.resources.save", {
        "program_id": "viernes-paranormal",
        "text": custom_text,
    }))["result"]

    assert saved["status"] == "saved"
    assert saved["story_resource_source"] == "manual"
    assert saved["story_resource_items"][0]["title"] == "La Escalera que Susurraba"

    response = server.handle(_request("programs.list", {}))["result"]
    viernes = next(p for p in response["programs"] if p["program_id"] == "viernes-paranormal")
    assert viernes["story_resource_source"] == "manual"
    assert "La Escalera que Susurraba" in viernes["story_resource_text"]

    retrieval = server.handle(_request("rag.retrieve_v3", {
        "query": "escalera que susurraba nombres madrugada casa vieja",
        "limit": 5,
    }))["result"]
    assert "program_story_templates_v1" in {item["document_id"] for item in retrieval["results"]}

    reset = server.handle(_request("programs.resources.reset", {"program_id": "viernes-paranormal"}))["result"]
    assert reset["status"] == "reset"
    assert reset["story_resource_source"] == "base"
    assert "La Casa que Respiraba" in reset["story_resource_text"]
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


def test_episodes_get_returns_the_saved_script_text(tmp_path, tmp_path_factory):
    server, service = _server(tmp_path)
    artifact_dir = tmp_path_factory.mktemp("artifact")
    script_path = artifact_dir / "script.txt"
    script_path.write_text("Escena 1: la casa vieja crujía en la noche.", encoding="utf-8")
    service.store.save_owned_story_artifact(
        story_id="ep_script", artifact_uri="kronara://sha256/s", path=str(script_path), sha256="s",
        created_at=100, program_id="viernes-paranormal",
        metadata={
            "title": "La casa vieja",
            "duration_seconds": 95.0,
            "generator_family": "groq",
            "music_path": "/runtime/music.wav",
            "sfx_cue_tags": ["footsteps", "door_creak"],
            "sfx_resolved_paths": {"footsteps": "/runtime/footsteps.wav"},
            "sfx_missing_tags": ["door_creak"],
        },
    )

    response = server.handle(_request("episodes.get", {"story_id": "ep_script"}))

    assert response["result"]["script"] == "Escena 1: la casa vieja crujía en la noche."
    assert response["result"]["title"] == "La casa vieja"
    assert response["result"]["program_id"] == "viernes-paranormal"
    assert response["result"]["generator_family"] == "groq"
    assert response["result"]["music_path"] == "/runtime/music.wav"
    assert response["result"]["sfx_cue_tags"] == ["footsteps", "door_creak"]
    assert response["result"]["sfx_resolved_paths"] == {"footsteps": "/runtime/footsteps.wav"}
    assert response["result"]["sfx_missing_tags"] == ["door_creak"]
    service.close()


def test_episodes_get_rejects_an_unknown_story_id(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(_request("episodes.get", {"story_id": "does-not-exist"}))

    assert response["error"]["code"] == -32602
    service.close()


def test_episodes_delete_removes_record_and_runtime_files(tmp_path):
    server, service = _server(tmp_path)
    runtime = tmp_path / "runtime"
    script_path = runtime / "artifacts" / "script.txt"
    video_dir = runtime / "artifacts" / "video" / "ep_delete"
    video_path = video_dir / "ep_delete.mp4"
    cover_path = runtime / "images" / "ep_delete.png"
    for path in (script_path, video_path, cover_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"owned episode file")
    service.store.save_owned_story_artifact(
        story_id="ep_delete",
        artifact_uri="kronara://sha256/delete",
        path=str(script_path),
        sha256="delete",
        created_at=100,
        metadata={"title": "Borrar", "video_path": str(video_path), "cover_image_path": str(cover_path)},
    )

    response = server.handle(_request("episodes.delete", {"story_id": "ep_delete"}))

    assert response["result"]["status"] == "deleted"
    assert not service.store.list_owned_story_artifacts(limit=10)
    assert not script_path.exists()
    assert not video_path.exists()
    assert not video_dir.exists()
    assert not cover_path.exists()
    service.close()


def test_run_diagnostics_exposes_quality_blocker_and_real_failed_phase(tmp_path):
    server, service = _server(tmp_path)
    story_id = "owned_diag_quality"
    story_run_id = f"story:{story_id}"
    content_run_id = f"content:{story_id}"
    service.store.append_event(content_run_id, "content.reddit_fallback_rss", {"signal_count": 1})
    service.store.append_event(story_run_id, "story.node", {"node": "concept_selection", "detail": "concept_1", "status": "running"})
    service.store.append_event(story_run_id, "story.node", {"node": "script_assembly", "detail": 247, "status": "running"})
    service.store.append_event(story_run_id, "story.node", {"node": "narration", "status": "running"})
    service.store.append_event(
        story_run_id,
        "story.quality_failed",
        {
            "quality_total": 74.0,
            "revision_count": 6,
            "blocking_dimensions": ["agency", "retention", "payoff"],
            "issues": ["La protagonista observa, pero no decide."],
            "critique_passed": False,
        },
    )
    service.store.append_event(story_run_id, "story.node", {"node": "guardian", "detail": "QUALITY_FAILED", "status": "blocked"})
    started = ToolTraceEvent.started(
        event_id="trace_diag_1",
        run_id=story_run_id,
        agent_id="story.critic",
        tool_id="model.complete",
        arguments={"task": "story.critique"},
        started_at=datetime.now(UTC),
    )
    service.store.save_tool_trace(
        started.finish(
            status="completed",
            finished_at=datetime.now(UTC),
            result_summary="Crítica rechazó por agencia y retención.",
        )
    )

    response = server.handle(_request("run.diagnostics", {"run_id": content_run_id}))

    result = response["result"]
    assert result["quality_failure"]["quality_total"] == 74.0
    phases = {phase["key"]: phase for phase in result["phases"]}
    assert phases["critica"]["status"] == "failed"
    assert "74.0/110" in phases["critica"]["detail"]
    assert phases["narracion"]["status"] == "completed"
    assert "bloqueo real fue Crítica" in phases["narracion"]["detail"]
    assert result["tool_events"][0]["tool_id"] == "model.complete"
    service.close()


def test_run_diagnostics_exposes_program_quality_blocker_as_critique(tmp_path):
    server, service = _server(tmp_path)
    story_id = "owned_diag_program_quality"
    story_run_id = f"story:{story_id}"
    content_run_id = f"content:{story_id}"
    service.store.append_event(content_run_id, "content.reddit_fallback_rss", {"signal_count": 1})
    service.store.append_event(story_run_id, "story.node", {"node": "script_assembly", "detail": 338, "status": "running"})
    service.store.append_event(story_run_id, "story.node", {"node": "narration", "status": "running"})
    service.store.append_event(
        story_run_id,
        "story.program_quality_failed",
        {
            "program_id": "viernes-paranormal",
            "findings": ["missing_clear_paranormal_threat", "missing_haunted_place_anchors"],
        },
    )
    service.store.append_event(story_run_id, "story.node", {"node": "guardian", "detail": "PROGRAM_QUALITY_FAILED", "status": "blocked"})

    response = server.handle(_request("run.diagnostics", {"run_id": content_run_id}))

    result = response["result"]
    phases = {phase["key"]: phase for phase in result["phases"]}
    assert result["program_quality_failure"]["program_id"] == "viernes-paranormal"
    assert phases["critica"]["status"] == "failed"
    assert "missing_clear_paranormal_threat" in phases["critica"]["detail"]
    assert phases["guardando"]["status"] == "pending"
    assert phases["narracion"]["status"] == "completed"
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


def test_static_program_story_templates_are_available_to_rag(tmp_path):
    server, service = _server(tmp_path)

    retrieval = server.handle(
        _request(
            "rag.retrieve_v3",
            {"query": "plantilla viernes paranormal niña espejo imágenes consistentes", "limit": 5},
            5,
        )
    )["result"]

    assert "program_story_templates_v1" in {item["document_id"] for item in retrieval["results"]}
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


def test_action_approve_executes_a_pending_create_episode_intent(tmp_path, monkeypatch):
    """The chat assistant can only ever PROPOSE a create_episode intent
    (see OperationsChatAgent); action.approve is what actually executes it,
    by looking the intent up server-side via its idempotency_key rather
    than trusting client-resupplied arguments. content_run itself is
    monkeypatched here since its real pipeline is already exercised end to
    end by test_production_content_vertical.py -- this test is about the
    propose/approve/execute wiring, not the pipeline."""
    server, service = _server(tmp_path)
    calls = []
    monkeypatch.setattr(
        service,
        "content_run",
        lambda params: calls.append(params)
        or {"status": "completed", "run_id": "content:x", "story": {"title": "La casa vieja"}},
    )

    chat = server.handle(
        _request(
            "operations.chat",
            {
                "schema_version": 1,
                "request_id": "chat_ep",
                "conversation_id": "conv_ep",
                "message": "Crea un episodio de Viernes Paranormal",
            },
        )
    )["result"]
    assert chat["action_intent"]["kind"] == "create_episode"
    key = chat["action_intent"]["idempotency_key"]

    approved = server.handle(_request("action.approve", {"idempotency_key": key}, 3))["result"]

    assert approved["status"] == "executed"
    assert approved["result"]["story"]["title"] == "La casa vieja"
    assert calls[0]["program_id"] == "viernes-paranormal"
    assert calls[0]["story_id"].startswith("owned_chat_")
    service.close()


def test_action_approve_only_executes_once_for_the_same_proposal(tmp_path, monkeypatch):
    server, service = _server(tmp_path)
    calls = []
    monkeypatch.setattr(
        service, "content_run", lambda params: calls.append(params) or {"status": "completed"}
    )
    chat = server.handle(
        _request(
            "operations.chat",
            {
                "schema_version": 1,
                "request_id": "chat_ep2",
                "conversation_id": "conv_ep2",
                "message": "Crea un episodio de Viernes Paranormal",
            },
        )
    )["result"]
    key = chat["action_intent"]["idempotency_key"]

    first = server.handle(_request("action.approve", {"idempotency_key": key}, 3))["result"]
    second = server.handle(_request("action.approve", {"idempotency_key": key}, 4))["result"]

    assert first["status"] == "executed"
    assert second["status"] == "not_found"
    assert len(calls) == 1
    service.close()


def test_action_approve_rejects_an_unknown_idempotency_key(tmp_path):
    server, service = _server(tmp_path)

    response = server.handle(_request("action.approve", {"idempotency_key": "does-not-exist"}))[
        "result"
    ]

    assert response["status"] == "not_found"
    assert response["result"] is None
    service.close()


def test_action_approve_inherits_the_content_run_pause_gate(tmp_path):
    """action.approve does not duplicate the pause check -- it delegates to
    content_run, which already enforces it. This confirms that inherited
    safety actually holds rather than assuming it."""
    server, service = _server(tmp_path)
    with service._lock:
        service._pending_intents["intent_key_1"] = {
            "kind": "create_episode",
            "arguments": {"program_id": "viernes-paranormal"},
        }
    server.handle(_request("operations.control_snapshot", {"paused": True}, 3))

    response = server.handle(_request("action.approve", {"idempotency_key": "intent_key_1"}, 4))

    assert response["error"]["code"] == -32602
    assert "global pause blocks content runs" in response["error"]["message"]
    service.close()
