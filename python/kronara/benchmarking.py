from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kronara.context import ContextBuilder, ContextItem, TrustLevel
from kronara.narrative_quality import NarrativeQualityEvaluator


@dataclass(frozen=True)
class BenchmarkResult:
    case_id: str
    passed: bool
    expected_pass: bool
    matched_expectation: bool
    findings: tuple[str, ...]


def run_golden_suite(path: Path) -> tuple[BenchmarkResult, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    evaluator = NarrativeQualityEvaluator()
    results: list[BenchmarkResult] = []
    for case in payload["cases"]:
        findings = list(evaluator.detect_antipatterns(case.get("text", "")))
        if case.get("external_context"):
            package = ContextBuilder().build(
                "verified policy",
                [
                    ContextItem(
                        case["case_id"],
                        case["external_context"],
                        "benchmark://external",
                        TrustLevel.UNTRUSTED,
                        100,
                    )
                ],
            )
            if package.injection_warnings:
                findings.append("prompt_injection")
        quality = evaluator.evaluate(case["scores"])
        passed = quality.passed and not findings
        expected = bool(case["expected_pass"])
        results.append(
            BenchmarkResult(
                case["case_id"],
                passed,
                expected,
                passed == expected,
                tuple(findings),
            )
        )
    return tuple(results)
