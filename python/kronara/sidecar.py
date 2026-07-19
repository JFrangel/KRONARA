from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from kronara.rpc import JsonRpcServer
from kronara.trends import RedditSignalExtractor, SourcePost


def _extract_trend(params: dict) -> dict:
    post = SourcePost(
        source_id=str(params["source_id"]),
        title=str(params["title"]),
        body=str(params.get("body", "")),
        score=int(params.get("score", 0)),
        comments=int(params.get("comments", 0)),
        created_at=int(params["created_at"]),
        source_uri=str(params["source_uri"]),
    )
    signal = RedditSignalExtractor().extract(post, now=int(params["now"]))
    return {key: value for key, value in asdict(signal).items() if key != "source_text"}


def serve(token: str) -> int:
    server = JsonRpcServer(token=token, methods={"trend.extract": _extract_trend})
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
