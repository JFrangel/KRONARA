import io
import json

import pytest

from kronara.authority_client import (
    ALLOWED_AUTHORITY_TOOLS,
    AuthorityInvocationError,
    StdioAuthorityClient,
)


def test_pexels_search_videos_is_an_allowed_authority_tool():
    # Mirrors sidecar_bridge.rs's ALLOWED_AUTHORITY_TOOLS on the Rust side --
    # both allowlists must agree or a live Pexels call is silently blocked
    # by the Python client before it ever reaches Rust.
    assert "pexels.search_videos" in ALLOWED_AUTHORITY_TOOLS


def test_stdio_authority_client_uses_nested_json_rpc_without_persisting_secrets():
    reader = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "authority-1",
                "result": {
                    "schema_version": 1,
                    "signals": [{"source_id": "safe-1", "theme_hint": "misterio familiar"}],
                },
            }
        )
        + "\n"
    )
    writer = io.StringIO()
    client = StdioAuthorityClient(reader=reader, writer=writer)

    result = client.invoke("reddit.list_signals", {"subreddits": ["Historias"]})

    request = json.loads(writer.getvalue())
    assert request == {
        "jsonrpc": "2.0",
        "id": "authority-1",
        "method": "authority.invoke",
        "params": {
            "tool_id": "reddit.list_signals",
            "arguments": {"subreddits": ["Historias"]},
        },
    }
    assert result["signals"][0]["source_id"] == "safe-1"


def test_stdio_authority_client_rejects_identity_mismatch_and_remote_error():
    mismatch = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": "wrong", "result": {}}) + "\n"
    )
    with pytest.raises(AuthorityInvocationError, match="identity"):
        StdioAuthorityClient(reader=mismatch, writer=io.StringIO()).invoke(
            "model.complete", {}
        )

    failure = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "authority-1",
                "error": {"code": -32020, "message": "tool blocked"},
            }
        )
        + "\n"
    )
    with pytest.raises(AuthorityInvocationError, match="tool blocked"):
        StdioAuthorityClient(reader=failure, writer=io.StringIO()).invoke(
            "model.complete", {}
        )


def test_stdio_authority_client_rejects_unapproved_tool_names():
    client = StdioAuthorityClient(reader=io.StringIO(), writer=io.StringIO())

    with pytest.raises(AuthorityInvocationError, match="not allowed"):
        client.invoke("shell.execute", {"command": "whoami"})
