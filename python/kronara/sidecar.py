from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from kronara.agent_catalog import AgentCatalog, KNOWN_TOOLS
from kronara.analytics import AnalysisRequest, AnalyticalToolkit
from kronara.evidence import EvidenceEngine
from kronara.narrative_quality import NarrativeQualityEvaluator
from kronara.research import ResearchPlanner, ResearchSynthesizer
from kronara.research_contracts import ResearchQuestion, SourceAssertion, SourceRecord
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


def _research_question(params: dict) -> ResearchQuestion:
    return ResearchQuestion(
        question_id=str(params["question_id"]),
        question=str(params["question"]),
        language=str(params.get("language", "es")),
        max_cost_usd=float(params["max_cost_usd"]),
        max_sources=int(params.get("max_sources", 12)),
        sensitive=bool(params.get("sensitive", False)),
    )


def _research_plan(params: dict) -> dict:
    return asdict(ResearchPlanner().plan(_research_question(params)))


def _source_record(params: dict) -> SourceRecord:
    assertions = tuple(
        SourceAssertion(
            claim_id=str(item["claim_id"]),
            subquestion_id=str(item["subquestion_id"]),
            text=str(item["text"]),
            kind=str(item["kind"]),
            stance=str(item["stance"]),
            confidence=float(item["confidence"]),
        )
        for item in params.get("assertions", ())
    )
    valid_until = params.get("valid_until")
    return SourceRecord(
        record_id=str(params["record_id"]),
        source_uri=str(params["source_uri"]),
        publisher=str(params["publisher"]),
        source_family=str(params["source_family"]),
        published_at=datetime.fromisoformat(str(params["published_at"])),
        retrieved_at=datetime.fromisoformat(str(params["retrieved_at"])),
        valid_until=datetime.fromisoformat(str(valid_until)) if valid_until else None,
        rights_mode=str(params["rights_mode"]),
        assertions=assertions,
        depends_on=tuple(str(item) for item in params.get("depends_on", ())),
    )


def _research_evaluate(params: dict) -> dict:
    question = _research_question(dict(params["question"]))
    plan = ResearchPlanner().plan(question)
    records = tuple(_source_record(dict(item)) for item in params.get("records", ()))
    as_of = max((record.retrieved_at for record in records), default=None)
    matrix = EvidenceEngine(now=as_of).build(
        records,
        expected_subquestion_ids=tuple(item.subquestion_id for item in plan.subquestions),
    )
    brief = ResearchSynthesizer().synthesize(plan, matrix)
    return {"plan": asdict(plan), "evidence": asdict(matrix), "brief": asdict(brief)}


def serve(token: str) -> int:
    server = JsonRpcServer(
        token=token,
        methods={
            "trend.extract": _extract_trend,
            "agent.capabilities": _agent_capabilities,
            "agent.evaluate_narrative": _evaluate_narrative,
            "analytics.execute": _analytics_execute,
            "research.plan": _research_plan,
            "research.evaluate": _research_evaluate,
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
