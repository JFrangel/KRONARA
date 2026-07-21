from __future__ import annotations

import sys
import traceback
from collections.abc import Callable, Mapping
from typing import Any


class JsonRpcServer:
    def __init__(
        self,
        token: str,
        protocol_version: int = 1,
        methods: Mapping[str, Callable[[dict[str, Any]], Any]] | None = None,
    ):
        self.token = token
        self.protocol_version = protocol_version
        self.authenticated = False
        self.methods = dict(methods or {})

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return self._error(request_id, -32600, "invalid request")
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "params must be an object")
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
        handler = self.methods.get(str(method))
        if handler is not None:
            try:
                return self._result(request_id, handler(params))
            except (KeyError, TypeError, ValueError) as error:
                return self._error(request_id, -32602, f"invalid params: {error}")
            except Exception:
                # The RPC caller only ever sees the generic message below --
                # never leak internals over the wire. But an unhandled
                # exception with zero trace anywhere (this used to just
                # vanish) is undiagnosable by anyone, including whoever is
                # running Kronara locally. stderr now lands in a real log
                # file (see SidecarProcess::spawn in sidecar_bridge.rs).
                traceback.print_exc(file=sys.stderr)
                return self._error(request_id, -32603, "internal error")
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
