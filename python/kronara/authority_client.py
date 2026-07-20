from __future__ import annotations

import json
from collections.abc import Mapping
from itertools import count
from typing import Any, Protocol, TextIO


ALLOWED_AUTHORITY_TOOLS = frozenset(
    {
        "model.health",
        "model.complete",
        "reddit.list_signals",
        "meta.metrics.read",
        "voice.synthesize",
        "publication.publish",
    }
)


class AuthorityInvocationError(RuntimeError):
    pass


class AuthorityClient(Protocol):
    def invoke(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class UnavailableAuthorityClient:
    def invoke(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        del arguments
        if tool_id not in ALLOWED_AUTHORITY_TOOLS:
            raise AuthorityInvocationError(f"authority tool is not allowed: {tool_id}")
        raise AuthorityInvocationError("Rust authority is unavailable in this execution")


class StdioAuthorityClient:
    """Synchronous nested JSON-RPC client used only while Rust owns the sidecar pipes."""

    def __init__(self, *, reader: TextIO, writer: TextIO):
        self.reader = reader
        self.writer = writer
        self._ids = count(1)

    def invoke(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_id not in ALLOWED_AUTHORITY_TOOLS:
            raise AuthorityInvocationError(f"authority tool is not allowed: {tool_id}")
        if not isinstance(arguments, dict):
            raise AuthorityInvocationError("authority arguments must be an object")
        request_id = f"authority-{next(self._ids)}"
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "authority.invoke",
            "params": {"tool_id": tool_id, "arguments": arguments},
        }
        self.writer.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.writer.flush()
        raw = self.reader.readline()
        if not raw:
            raise AuthorityInvocationError("Rust authority closed the RPC channel")
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AuthorityInvocationError("Rust authority returned invalid JSON") from error
        if response.get("id") != request_id:
            raise AuthorityInvocationError("authority response identity mismatch")
        if isinstance(response.get("error"), Mapping):
            message = str(response["error"].get("message") or "authority invocation failed")
            raise AuthorityInvocationError(message)
        result = response.get("result")
        if not isinstance(result, dict):
            raise AuthorityInvocationError("authority result must be an object")
        return dict(result)
