from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from kronara.virality import (
    PlatformFeatureVector,
    PlatformObservation,
    ViralityModel,
)


START = datetime(2026, 1, 1, tzinfo=UTC)


def test_feature_vector_rejects_invalid_rates_and_saturation():
    with pytest.raises(ValueError, match="saturation"):
        _features("bad", platform="facebook_reels", signal=0.5, saturation=1.1)


def test_model_abstains_when_platform_sample_is_insufficient():
    observations = tuple(
        _observation(index, platform="facebook_reels", outcome=index % 2)
        for index in range(8)
    )
    model = ViralityModel(minimum_observations=20)
    version = model.fit(observations)

    forecast = model.predict(_features("candidate", "facebook_reels", signal=0.8))

    assert version.platform_models == ()
    assert forecast.status == "abstained"
    assert forecast.probability is None
    assert forecast.reason == "insufficient_platform_data"
    assert forecast.guaranteed is False


def test_training_uses_temporal_holdout_without_leakage():
    observations = tuple(
        _observation(index, "facebook_reels", outcome=int(index >= 15))
        for index in range(30)
    )
    version = ViralityModel(minimum_observations=20).fit(observations)
    platform_model = version.platform_models[0]

    assert platform_model.training_end < platform_model.validation_start
    assert platform_model.observation_count == 30
    assert 0 <= platform_model.brier_score <= 1
    assert {weight.feature for weight in platform_model.weights} >= {
        "completion_rate",
        "velocity_signal",
        "acceleration_signal",
        "saturation_headroom",
        "freshness",
    }


def test_forecasts_are_bounded_platform_specific_and_never_guaranteed():
    facebook = tuple(
        _observation(index, "facebook_reels", outcome=int(index >= 15))
        for index in range(30)
    )
    youtube = tuple(
        _observation(index, "youtube_shorts", outcome=int(index < 15))
        for index in range(30)
    )
    model = ViralityModel(minimum_observations=20)
    model.fit(facebook + youtube)

    facebook_forecast = model.predict(
        _features("fb-candidate", "facebook_reels", signal=0.85)
    )
    youtube_forecast = model.predict(
        _features("yt-candidate", "youtube_shorts", signal=0.85)
    )

    assert facebook_forecast.status == "estimated"
    assert youtube_forecast.status == "estimated"
    assert 0 <= facebook_forecast.probability <= 1
    assert facebook_forecast.interval[0] <= facebook_forecast.probability <= facebook_forecast.interval[1]
    assert facebook_forecast.probability != youtube_forecast.probability
    assert facebook_forecast.guaranteed is False
    assert "no es una garantía" in facebook_forecast.explanation
    assert "algorithm_change" in facebook_forecast.unknown_factors


def test_model_version_and_prediction_are_reproducible():
    observations = tuple(
        _observation(index, "facebook_reels", outcome=int(index >= 15))
        for index in range(30)
    )
    first = ViralityModel(minimum_observations=20)
    second = ViralityModel(minimum_observations=20)

    first_version = first.fit(observations)
    second_version = second.fit(tuple(reversed(observations)))
    candidate = _features("candidate", "facebook_reels", signal=0.7)

    assert first_version.model_version == second_version.model_version
    assert first.predict(candidate).probability == second.predict(candidate).probability


def _features(
    vector_id: str,
    platform: str,
    signal: float,
    *,
    saturation: float = 0.3,
) -> PlatformFeatureVector:
    return PlatformFeatureVector(
        schema_version=1,
        vector_id=vector_id,
        content_id=f"content-{vector_id}",
        platform=platform,
        observed_at=START,
        age_hours=12.0,
        completion_rate=0.25 + signal * 0.6,
        share_rate=0.01 + signal * 0.08,
        replay_rate=0.02 + signal * 0.12,
        velocity_per_hour=10 + signal * 990,
        acceleration_per_hour2=-5 + signal * 30,
        saturation_index=saturation,
        duration_seconds=45.0,
    )


def _observation(index: int, platform: str, outcome: int) -> PlatformObservation:
    signal = index / 29
    features = replace(
        _features(f"{platform}-{index}", platform, signal=signal),
        observed_at=START + timedelta(days=index),
        age_hours=6 + index,
        saturation_index=min(0.95, 0.1 + index / 40),
    )
    return PlatformObservation(
        observation_id=f"observation-{platform}-{index}",
        features=features,
        outcome_viral=outcome,
        finalized_at=START + timedelta(days=index, hours=72),
    )
