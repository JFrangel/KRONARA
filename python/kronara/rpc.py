from __future__ import annotations

from typing import Any


class JsonRpcServer:
    def __init__(self, token: str, protocol_version: int = 1):
        self.token = token
        self.protocol_version = protocol_version
        self.authenticated = False

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if method == "handshake":
            if params.get("token") != self.token:
                return self._error(request_id, -32001, "authentication failed")
            if params.get("protocol_version") != self.protocol_version:
                return self._error(request_id, -32002, "protocol version mismatch")
            self.authenticated = True
            return self._result(request_id, {"protocol_version": self.protocol_version})
        if not self.authenticated:
            return self._error(request_id, -32001, "handshake required")
        if method == "heartbeat":
            return self._result(request_id, {"status": "ok"})
        return self._error(request_id, -32601, "method not found")

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

