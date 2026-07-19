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
from kronara.improvement import (
    ADMINISTRATIVE_PARAMETERS,
    AUTOMATIC_PARAMETERS,
    SUPERVISED_PARAMETERS,
    CandidateEvaluation,
    CandidateVersion,
    EvaluationSet,
    ImprovementEngine,
)
from kronara.narrative_quality import NarrativeQualityEvaluator
from kronara.performance import MetricSnapshot, PerformanceScientist
from kronara.rag_v2 import (
    DeterministicHashEmbedder,
    IngestDocument,
    RAGEvaluation,
    RAGEvaluationCase,
    RAGEvaluator,
    RAGPromotionGate,
    RAGV2Index,
)
from kronara.research import ResearchPlanner, ResearchSynthesizer
from kronara.research_contracts import ResearchQuestion, SourceAssertion, SourceRecord
from kronara.rpc import JsonRpcServer
from kronara.trends import RedditSignalExtractor, SourcePost
from kronara.virality import PlatformFeatureVector, PlatformObservation, ViralityModel


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


def _metric_snapshot(params: dict) -> MetricSnapshot:
    return MetricSnapshot(
        schema_version=int(params["schema_version"]),
        snapshot_id=str(params["snapshot_id"]),
        content_id=str(params["content_id"]),
        platform=str(params["platform"]),
        published_at=datetime.fromisoformat(str(params["published_at"])),
        observed_at=datetime.fromisoformat(str(params["observed_at"])),
        metric_window_hours=int(params["metric_window_hours"]),
        impressions=int(params["impressions"]),
        starts=int(params["starts"]),
        completions=int(params["completions"]),
        replays=int(params["replays"]),
        shares=int(params["shares"]),
        watch_time_seconds=float(params["watch_time_seconds"]),
        duration_seconds=float(params["duration_seconds"]),
        voice_id=str(params["voice_id"]),
        topic=str(params["topic"]),
        hook_id=str(params["hook_id"]),
        publication_hour=int(params["publication_hour"]),
        audience_segment=str(params["audience_segment"]),
    )


def _performance_diagnose(params: dict) -> dict:
    snapshots = tuple(_metric_snapshot(dict(item)) for item in params.get("snapshots", ()))
    return asdict(PerformanceScientist().diagnose(snapshots))


def _platform_features(params: dict) -> PlatformFeatureVector:
    return PlatformFeatureVector(
        schema_version=int(params["schema_version"]),
        vector_id=str(params["vector_id"]),
        content_id=str(params["content_id"]),
        platform=str(params["platform"]),
        observed_at=datetime.fromisoformat(str(params["observed_at"])),
        age_hours=float(params["age_hours"]),
        completion_rate=float(params["completion_rate"]),
        share_rate=float(params["share_rate"]),
        replay_rate=float(params["replay_rate"]),
        velocity_per_hour=float(params["velocity_per_hour"]),
        acceleration_per_hour2=float(params["acceleration_per_hour2"]),
        saturation_index=float(params["saturation_index"]),
        duration_seconds=float(params["duration_seconds"]),
    )


def _virality_evaluate(params: dict) -> dict:
    observations = tuple(
        PlatformObservation(
            observation_id=str(item["observation_id"]),
            features=_platform_features(dict(item["features"])),
            outcome_viral=int(item["outcome_viral"]),
            finalized_at=datetime.fromisoformat(str(item["finalized_at"])),
        )
        for item in params.get("observations", ())
    )
    model = ViralityModel()
    version = model.fit(observations)
    forecast = model.predict(_platform_features(dict(params["candidate"])))
    return {"model": _json_safe(asdict(version)), "forecast": _json_safe(asdict(forecast))}


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _candidate_version(params: dict) -> CandidateVersion:
    return CandidateVersion(
        version_id=str(params["version_id"]),
        parameter=str(params["parameter"]),
        config_hash=str(params["config_hash"]),
        created_at=datetime.fromisoformat(str(params["created_at"])),
        expires_at=datetime.fromisoformat(str(params["expires_at"])),
    )


def _candidate_evaluation(params: dict) -> CandidateEvaluation:
    raw_set = dict(params["evaluation_set"])
    return CandidateEvaluation(
        evaluation_id=str(params["evaluation_id"]),
        evaluation_set=EvaluationSet(
            set_id=str(raw_set["set_id"]),
            version=int(raw_set["version"]),
            frozen=bool(raw_set["frozen"]),
            content_hash=str(raw_set["content_hash"]),
            case_count=int(raw_set["case_count"]),
        ),
        sample_size=int(params["sample_size"]),
        champion_score=float(params["champion_score"]),
        challenger_score=float(params["challenger_score"]),
        safety_regressions=tuple(str(item) for item in params.get("safety_regressions", ())),
        cost_change_ratio=float(params["cost_change_ratio"]),
        platform_stability=float(params["platform_stability"]),
    )


def _improvement_status(_: dict) -> dict:
    return {
        "schema_version": 1,
        "automatic_parameters": sorted(AUTOMATIC_PARAMETERS),
        "supervised_parameters": sorted(SUPERVISED_PARAMETERS),
        "administrative_parameters": sorted(ADMINISTRATIVE_PARAMETERS),
        "minimum_sample": 100,
        "minimum_relative_lift": 0.05,
        "maximum_cost_increase": 0.15,
        "minimum_platform_stability": 0.8,
        "direct_policy_mutation": False,
    }


def _improvement_evaluate(params: dict) -> dict:
    as_of = datetime.fromisoformat(str(params["as_of"]))
    engine = ImprovementEngine(now=lambda: as_of)
    decision = engine.evaluate(
        _candidate_version(dict(params["champion"])),
        _candidate_version(dict(params["challenger"])),
        _candidate_evaluation(dict(params["evaluation"])),
    )
    return asdict(decision)


def _rag_evaluate(params: dict) -> dict:
    documents = tuple(params.get("documents", ()))
    raw_cases = tuple(params.get("cases", ()))
    k = int(params.get("k", 8))
    now = int(params["now"])
    if not 1 <= k <= 50:
        raise ValueError("k must be between 1 and 50")
    if now < 0:
        raise ValueError("now cannot be negative")
    if not 1 <= len(documents) <= 500:
        raise ValueError("rag evaluation requires at most 500 documents and at least one")
    if not 1 <= len(raw_cases) <= 100:
        raise ValueError("rag evaluation requires at most 100 cases and at least one")
    total_characters = sum(
        len(str(dict(item).get("title", "")))
        + len(str(dict(item).get("content", "")))
        for item in documents
    )
    if total_characters > 2_000_000:
        raise ValueError("rag evaluation document budget exceeds 2000000 characters")
    index = RAGV2Index(DeterministicHashEmbedder())
    for raw_document in documents:
        item = dict(raw_document)
        index.upsert(
            IngestDocument(
                document_id=str(item["document_id"]),
                title=str(item["title"]),
                content=str(item["content"]),
                rights_mode=str(item["rights_mode"]),
                language=str(item["language"]),
                scope=str(item["scope"]),
                valid_from=int(item["valid_from"]),
                valid_until=(
                    int(item["valid_until"])
                    if item.get("valid_until") is not None
                    else None
                ),
                confidence=float(item.get("confidence", 1.0)),
                version=int(item.get("version", 1)),
            )
        )
    for raw_edge in params.get("edges", ()):
        edge = dict(raw_edge)
        index.link_documents(
            str(edge["source_id"]),
            str(edge["target_id"]),
            relation=str(edge.get("relation", "related")),
            weight=float(edge.get("weight", 1.0)),
        )
    cases = tuple(
        RAGEvaluationCase(
            query=str(item["query"]),
            relevant_document_ids=tuple(
                str(identifier) for identifier in item["relevant_document_ids"]
            ),
        )
        for item in raw_cases
    )
    evaluation = RAGEvaluator().evaluate(
        index,
        cases,
        now=now,
        k=k,
    )
    promotion = None
    if params.get("baseline") is not None:
        baseline = RAGEvaluation(**dict(params["baseline"]))
        gate = RAGPromotionGate(**dict(params.get("promotion_thresholds", {})))
        promotion = asdict(gate.evaluate(baseline, evaluation))
    return {"evaluation": asdict(evaluation), "promotion": promotion}


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
            "performance.diagnose": _performance_diagnose,
            "virality.evaluate": _virality_evaluate,
            "improvement.status": _improvement_status,
            "improvement.evaluate": _improvement_evaluate,
            "rag.evaluate": _rag_evaluate,
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
