from __future__ import annotations

import argparse
import json
import sys

from kronara.rpc import JsonRpcServer


def serve(token: str) -> int:
    server = JsonRpcServer(token=token)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {error}"},
            }
        print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Kronara cognitive sidecar")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    return serve(args.token)


if __name__ == "__main__":
    raise SystemExit(main())

