from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from kronara.agent_catalog import AgentCatalog, KNOWN_TOOLS
from kronara.analytics import AnalysisRequest, AnalyticalToolkit
from kronara.narrative_quality import NarrativeQualityEvaluator
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


def _resource_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _agent_capabilities(_: dict) -> dict:
    root = _resource_root()
    catalog = AgentCatalog.load(root / "config" / "agents")
    skill_payload = json.loads(
        (root / "config" / "skills" / "catalog.v1.json").read_text(encoding="utf-8")
    )
    return {
        "schema_version": 1,
        "agents": list(catalog.agent_ids),
        "skills": [item["skill_id"] for item in skill_payload["skills"]],
        "tools": sorted(KNOWN_TOOLS),
        "arbitrary_shell": False,
        "private_reasoning_persisted": False,
    }


def _evaluate_narrative(params: dict) -> dict:
    evaluator = NarrativeQualityEvaluator()
    report = evaluator.evaluate(params["scores"])
    antipatterns = evaluator.detect_antipatterns(str(params.get("text", "")))
    return {
        "passed": report.passed and not antipatterns,
        "total": report.total,
        "blocking_dimensions": list(report.blocking_dimensions),
        "antipatterns": list(antipatterns),
    }


def _analytics_execute(params: dict) -> dict:
    request = AnalysisRequest(
        operation=str(params["operation"]),
        inputs=dict(params["inputs"]),
        unit=str(params["unit"]) if params.get("unit") is not None else None,
        assumptions=tuple(str(item) for item in params.get("assumptions", ())),
    )
    return asdict(AnalyticalToolkit().execute(request))


def serve(token: str) -> int:
    server = JsonRpcServer(
        token=token,
        methods={
            "trend.extract": _extract_trend,
            "agent.capabilities": _agent_capabilities,
            "agent.evaluate_narrative": _evaluate_narrative,
            "analytics.execute": _analytics_execute,
        },
    )
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
