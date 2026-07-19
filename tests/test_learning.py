from kronara.learning import ExperimentResult, LearningEngine, LearningState


def test_learning_does_not_promote_voice_with_small_sample():
    result = ExperimentResult(
        hypothesis_id="h1",
        sample_size=12,
        baseline_completion=0.4,
        treatment_completion=0.6,
    )

    decision = LearningEngine(minimum_sample=100).evaluate(result)

    assert decision.state is LearningState.TESTING
    assert decision.reason == "insufficient_sample"


def test_learning_promotes_material_retention_gain():
    result = ExperimentResult(
        hypothesis_id="h1",
        sample_size=500,
        baseline_completion=0.40,
        treatment_completion=0.46,
    )

    decision = LearningEngine(minimum_sample=100, minimum_lift=0.05).evaluate(result)

    assert decision.state is LearningState.PROMOTED

