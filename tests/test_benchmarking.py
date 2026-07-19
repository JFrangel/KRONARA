from pathlib import Path

from kronara.benchmarking import run_golden_suite


def test_golden_suite_matches_all_expected_outcomes():
    suite = Path(__file__).parents[1] / "benchmarks" / "golden" / "narrative-runtime.v1.json"

    results = run_golden_suite(suite)

    assert len(results) == 6
    assert all(result.matched_expectation for result in results)
    assert "prompt_injection" in next(
        result.findings for result in results if result.case_id == "copied_source_instruction"
    )
