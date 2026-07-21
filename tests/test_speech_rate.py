from kronara.speech_rate import DEFAULT_WORDS_PER_SECOND, SpeechRateLearner


def learner(tmp_path, name="speech_rate.db"):
    return SpeechRateLearner(tmp_path / name).initialize()


def test_estimate_returns_the_cold_start_prior_when_no_samples_exist(tmp_path):
    store = learner(tmp_path)

    result = store.estimate("es-BO-SofiaNeural")

    assert result.words_per_second == DEFAULT_WORDS_PER_SECOND
    assert result.sample_count == 0
    assert result.learned is False


def test_record_updates_the_estimate_to_the_real_observed_rate(tmp_path):
    store = learner(tmp_path)

    store.record("es-BO-SofiaNeural", 200, 50.0)  # 4.0 words/sec
    result = store.estimate("es-BO-SofiaNeural")

    assert result.words_per_second == 4.0
    assert result.sample_count == 1
    assert result.learned is True


def test_record_accumulates_as_a_true_running_average_not_a_mean_of_rates(tmp_path):
    """100 words/50s (2.0 wps) then 300 words/50s (6.0 wps) must average to
    total_words/total_seconds = 400/100 = 4.0, not (2.0+6.0)/2 = 4.0 by
    coincidence here -- use an asymmetric second sample to actually
    distinguish the two formulas."""
    store = learner(tmp_path)

    store.record("v1", 100, 50.0)  # 2.0 wps
    store.record("v1", 300, 30.0)  # 10.0 wps
    result = store.estimate("v1")

    # naive mean-of-rates would give (2.0+10.0)/2 = 6.0; the correct
    # words-total/seconds-total average is 400/80 = 5.0.
    assert result.words_per_second == 5.0
    assert result.sample_count == 2


def test_estimate_is_scoped_per_voice_id(tmp_path):
    store = learner(tmp_path)

    store.record("voice-a", 400, 100.0)  # 4.0 wps

    assert store.estimate("voice-a").words_per_second == 4.0
    assert store.estimate("voice-b").learned is False


def test_learner_persists_across_reopening_the_same_database_file(tmp_path):
    db_path = tmp_path / "speech_rate.db"
    first = SpeechRateLearner(db_path).initialize()
    first.record("es-BO-SofiaNeural", 300, 100.0)  # 3.0 wps
    first.close()

    reopened = SpeechRateLearner(db_path).initialize()
    result = reopened.estimate("es-BO-SofiaNeural")

    assert result.words_per_second == 3.0
    assert result.sample_count == 1


def test_record_ignores_non_positive_word_count_or_seconds(tmp_path):
    store = learner(tmp_path)

    store.record("v1", 0, 10.0)
    store.record("v1", 10, 0.0)
    store.record("v1", -5, 10.0)

    assert store.estimate("v1").learned is False
