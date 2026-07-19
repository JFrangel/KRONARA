import math

import pytest

from kronara.analytics import AnalysisInputError, AnalysisRequest, AnalyticalToolkit


def test_describe_ignores_missing_values_and_reports_units():
    trace = AnalyticalToolkit().execute(
        AnalysisRequest(
            "describe",
            {"values": [1.0, None, 3.0, 5.0]},
            unit="seconds",
        )
    )

    assert trace.result == {
        "count": 3,
        "missing": 1,
        "mean": 3.0,
        "median": 3.0,
        "minimum": 1.0,
        "maximum": 5.0,
    }
    assert trace.unit == "seconds"
    assert len(trace.input_hash) == 64


def test_rate_comparison_returns_lift_and_wilson_intervals():
    trace = AnalyticalToolkit().execute(
        AnalysisRequest(
            "compare_rates",
            {
                "baseline_successes": 40,
                "baseline_total": 100,
                "treatment_successes": 55,
                "treatment_total": 100,
            },
            unit="completion_rate",
        )
    )

    assert trace.result["baseline_rate"] == 0.4
    assert trace.result["treatment_rate"] == 0.55
    assert math.isclose(trace.result["absolute_lift"], 0.15)
    assert math.isclose(trace.result["relative_lift"], 0.375)
    assert trace.result["baseline_interval"][0] < 0.4 < trace.result["baseline_interval"][1]


def test_rate_comparison_rejects_missing_or_invalid_denominators():
    toolkit = AnalyticalToolkit()

    with pytest.raises(AnalysisInputError, match="denominator"):
        toolkit.execute(
            AnalysisRequest(
                "compare_rates",
                {
                    "baseline_successes": 1,
                    "baseline_total": 0,
                    "treatment_successes": 2,
                    "treatment_total": 3,
                },
            )
        )


def test_funnel_reports_stage_dropoff_without_claiming_causality():
    trace = AnalyticalToolkit().execute(
        AnalysisRequest(
            "funnel",
            {"stages": [["impressions", 1000], ["started", 600], ["completed", 240]]},
            unit="viewers",
        )
    )

    assert trace.result["overall_conversion"] == 0.24
    assert trace.result["transitions"][0]["dropoff_rate"] == 0.4
    assert "descriptive_not_causal" in trace.warnings


def test_robust_outliers_uses_median_absolute_deviation():
    trace = AnalyticalToolkit().execute(
        AnalysisRequest("robust_outliers", {"values": [10, 10, 11, 9, 100]})
    )

    assert trace.result["outliers"] == [100.0]
    assert trace.result["median"] == 10.0


def test_unknown_operation_fails_closed():
    with pytest.raises(AnalysisInputError, match="unsupported operation"):
        AnalyticalToolkit().execute(AnalysisRequest("run_python", {}))


def test_retention_curve_finds_largest_dropoff_without_claiming_cause():
    trace = AnalyticalToolkit().execute(
        AnalysisRequest(
            "retention_curve",
            {
                "starts": 1000,
                "duration_seconds": 60,
                "checkpoints": [[0, 1000], [3, 800], [15, 400], [60, 250]],
            },
            unit="viewers",
        )
    )

    assert trace.result["points"][1]["retention_rate"] == 0.8
    assert trace.result["largest_dropoff"]["from_second"] == 3.0
    assert trace.result["largest_dropoff"]["to_second"] == 15.0
    assert trace.result["completion_rate"] == 0.25
    assert "descriptive_not_causal" in trace.warnings


def test_minimum_sample_size_increases_when_detectable_lift_gets_smaller():
    toolkit = AnalyticalToolkit()
    large_effect = toolkit.execute(
        AnalysisRequest(
            "minimum_sample_size",
            {"baseline_rate": 0.4, "minimum_detectable_absolute_lift": 0.1},
        )
    )
    small_effect = toolkit.execute(
        AnalysisRequest(
            "minimum_sample_size",
            {"baseline_rate": 0.4, "minimum_detectable_absolute_lift": 0.03},
        )
    )

    assert large_effect.result["per_variant"] > 0
    assert small_effect.result["per_variant"] > large_effect.result["per_variant"]
    assert small_effect.result["total_for_two_variants"] == 2 * small_effect.result["per_variant"]
