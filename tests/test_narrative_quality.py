from kronara.narrative_quality import NarrativeQualityEvaluator


def test_quality_gate_requires_total_and_every_dimension():
    evaluator = NarrativeQualityEvaluator()
    strong = {dimension: 8 for dimension in evaluator.dimensions}
    weak = {dimension: 8 for dimension in evaluator.dimensions}
    weak["originality"] = 6

    assert evaluator.evaluate(strong).passed is True
    report = evaluator.evaluate(weak)
    assert report.passed is False
    assert "originality" in report.blocking_dimensions


def test_quality_gate_flags_known_narrative_antipatterns():
    report = NarrativeQualityEvaluator().detect_antipatterns(
        "Todo era un sueño. De repente aparece un villano sin ninguna pista previa."
    )

    assert "dream_reset" in report
    assert "unseeded_twist" in report
