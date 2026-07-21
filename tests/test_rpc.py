from kronara.rpc import JsonRpcServer


def test_rpc_requires_authenticated_handshake_before_methods():
    server = JsonRpcServer(token="secret")

    denied = server.handle({"jsonrpc": "2.0", "id": 1, "method": "heartbeat", "params": {}})
    accepted = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        }
    )

    assert denied["error"]["code"] == -32001
    assert accepted["result"]["protocol_version"] == 1


def test_rpc_dispatches_only_explicitly_registered_methods():
    server = JsonRpcServer(token="secret", methods={"trend.score": lambda params: params["score"] * 2})
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        }
    )

    accepted = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "trend.score", "params": {"score": 4}}
    )
    denied = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "shell.execute", "params": {}}
    )

    assert accepted["result"] == 8
    assert denied["error"]["code"] == -32601


def test_rpc_converts_unexpected_handler_failures_to_sanitized_internal_errors(capsys):
    def fail(_):
        raise RuntimeError("provider leaked secret-value")

    server = JsonRpcServer(token="secret", methods={"safe.method": fail})
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "handshake",
            "params": {"token": "secret", "protocol_version": 1},
        }
    )

    response = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "safe.method", "params": {}}
    )

    assert response["error"]["code"] == -32603
    assert "secret-value" not in response["error"]["message"]
    # The RPC wire never leaks it -- but it must land SOMEWHERE (stderr,
    # which SidecarProcess::spawn redirects to a real log file) or a real
    # failure is undiagnosable by anyone, including whoever runs Kronara.
    assert "secret-value" in capsys.readouterr().err
