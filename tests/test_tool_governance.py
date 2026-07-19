from kronara.tools import ToolRegistry, ToolSpec


def test_registry_denies_tools_outside_agent_allowlist():
    registry = ToolRegistry(
        [ToolSpec("publication.publish", lambda _: {"remote_id": "1"}, side_effect=True)]
    )

    result = registry.invoke("writer", (), "publication.publish", {"token": "secret"})

    assert result.ok is False
    assert result.error_code == "TOOL_NOT_ALLOWED"
    assert "secret" not in repr(result)


def test_registry_stops_repeated_identical_tool_loop():
    registry = ToolRegistry(
        [ToolSpec("research.search", lambda args: {"query": args["query"]})],
        repeat_limit=2,
    )

    first = registry.invoke("researcher", ("research.search",), "research.search", {"query": "x"})
    second = registry.invoke("researcher", ("research.search",), "research.search", {"query": "x"})
    third = registry.invoke("researcher", ("research.search",), "research.search", {"query": "x"})

    assert first.ok and second.ok
    assert third.error_code == "TOOL_LOOP_DETECTED"


def test_registry_opens_circuit_after_repeated_provider_failures():
    def broken(_):
        raise TimeoutError("provider unavailable")

    registry = ToolRegistry([ToolSpec("model.generate", broken)], failure_threshold=2)

    one = registry.invoke("writer", ("model.generate",), "model.generate", {})
    two = registry.invoke("writer", ("model.generate",), "model.generate", {"attempt": 2})
    three = registry.invoke("writer", ("model.generate",), "model.generate", {"attempt": 3})

    assert one.error_code == "TOOL_FAILED"
    assert two.error_code == "TOOL_FAILED"
    assert three.error_code == "TOOL_CIRCUIT_OPEN"


def test_circuit_recovers_after_cooldown_and_success_resets_failures():
    now = [100.0]
    healthy = [False]

    def provider(_):
        if not healthy[0]:
            raise TimeoutError("down")
        return {"ok": True}

    registry = ToolRegistry(
        [ToolSpec("model.generate", provider)],
        failure_threshold=1,
        cooldown_seconds=10,
        clock=lambda: now[0],
    )

    assert registry.invoke("writer", ("model.generate",), "model.generate", {}).error_code == "TOOL_FAILED"
    assert registry.invoke("writer", ("model.generate",), "model.generate", {"n": 1}).error_code == "TOOL_CIRCUIT_OPEN"
    now[0] += 11
    healthy[0] = True
    assert registry.invoke("writer", ("model.generate",), "model.generate", {"n": 2}).ok

    healthy[0] = False
    assert registry.invoke("writer", ("model.generate",), "model.generate", {"n": 3}).error_code == "TOOL_FAILED"


def test_late_tool_result_is_rejected_as_timeout():
    now = [0.0]

    def slow(_):
        now[0] = 2.0
        return {"late": True}

    registry = ToolRegistry(
        [ToolSpec("research.search", slow, timeout_seconds=1.0)],
        clock=lambda: now[0],
    )

    result = registry.invoke("researcher", ("research.search",), "research.search", {})

    assert result.ok is False
    assert result.error_code == "TOOL_TIMEOUT"
