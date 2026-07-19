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

