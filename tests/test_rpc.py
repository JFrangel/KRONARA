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
