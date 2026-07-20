import pytest

from kronara.audio_mix import DuckingEnvelope, SfxCue, build_mix_filters, match_sfx_cues


# ---- DuckingEnvelope --------------------------------------------------------


def test_ducking_envelope_boundaries_are_exact():
    env = DuckingEnvelope(narration_start_s=2.0, narration_end_s=12.0, duck_gain=0.1, fade_s=0.2)
    assert env.pre_roll_s == 2.0
    assert env.duck_in_end_s == 2.2
    assert env.duck_out_start_s == 11.8
    assert env.duck_out_end_s == 12.0


def test_ducking_expression_contains_exact_numeric_boundaries():
    env = DuckingEnvelope(narration_start_s=2.0, narration_end_s=12.0, duck_gain=0.1, fade_s=0.2)
    expr = env.as_ffmpeg_expression()
    assert "lt(t,2.000)" in expr
    assert "lt(t,2.200)" in expr
    assert "lt(t,11.800)" in expr
    assert "lt(t,12.000)" in expr
    assert "0.1000" in expr


def test_ducking_volume_filter_wraps_expression_with_labels():
    env = DuckingEnvelope(narration_start_s=0.0, narration_end_s=5.0)
    filter_str = env.as_volume_filter(label_in="1:a", label_out="music_env")
    assert filter_str.startswith("[1:a]volume=eval=frame:volume='")
    assert filter_str.endswith("[music_env]")


def test_ducking_envelope_rejects_invalid_ranges():
    with pytest.raises(ValueError):
        DuckingEnvelope(narration_start_s=5.0, narration_end_s=5.0)
    with pytest.raises(ValueError):
        DuckingEnvelope(narration_start_s=0.0, narration_end_s=5.0, duck_gain=0.0)
    with pytest.raises(ValueError):
        DuckingEnvelope(narration_start_s=0.0, narration_end_s=5.0, duck_gain=1.5)


def test_short_narration_still_produces_valid_monotonic_boundaries():
    """A narration shorter than 2*fade_s must not produce duck_out_start before
    duck_in_end (the max() clamps in the properties exist exactly for this)."""
    env = DuckingEnvelope(narration_start_s=0.0, narration_end_s=0.1, fade_s=0.2)
    assert env.duck_out_start_s >= env.duck_in_end_s
    assert env.duck_out_end_s >= env.duck_out_start_s


# ---- match_sfx_cues ----------------------------------------------------------


class _Boundary:
    def __init__(self, word, offset_ms):
        self.word = word
        self.offset_ms = offset_ms
        self.duration_ms = 200


def test_matches_known_keyword_at_exact_offset():
    boundaries = [_Boundary("La", 0), _Boundary("puerta", 850), _Boundary("cruje", 1100)]
    cues = match_sfx_cues(boundaries)
    assert len(cues) == 1
    assert cues[0].tag == "door_creak"
    assert cues[0].offset_ms == 850
    assert cues[0].word == "puerta"


def test_ignores_words_not_in_the_keyword_map():
    boundaries = [_Boundary("Mara", 0), _Boundary("camina", 300), _Boundary("lento", 600)]
    assert match_sfx_cues(boundaries) == ()


def test_strips_punctuation_before_matching():
    boundaries = [_Boundary("¡Pasos!", 500)]
    cues = match_sfx_cues(boundaries)
    assert len(cues) == 1
    assert cues[0].tag == "footsteps"


def test_cooldown_suppresses_rapid_repeat_of_the_same_tag():
    boundaries = [
        _Boundary("puerta", 0),
        _Boundary("puerta", 1000),  # within 4000ms cooldown -> suppressed
        _Boundary("puerta", 5000),  # past cooldown -> allowed
    ]
    cues = match_sfx_cues(boundaries, cooldown_ms=4000)
    assert [c.offset_ms for c in cues] == [0, 5000]


def test_different_tags_are_not_subject_to_each_others_cooldown():
    boundaries = [_Boundary("puerta", 0), _Boundary("pasos", 100)]
    cues = match_sfx_cues(boundaries, cooldown_ms=4000)
    assert len(cues) == 2


def test_max_cues_caps_the_total():
    boundaries = [_Boundary("puerta", i * 5000) for i in range(20)]
    cues = match_sfx_cues(boundaries, cooldown_ms=1000, max_cues=3)
    assert len(cues) == 3


def test_custom_keyword_map_overrides_default():
    boundaries = [_Boundary("lluvia", 200)]
    cues = match_sfx_cues(boundaries, keyword_map={"lluvia": "rain"})
    assert cues[0].tag == "rain"


# ---- build_mix_filters --------------------------------------------------------


def test_build_mix_filters_includes_ducked_music_and_amix_with_normalize_off():
    env = DuckingEnvelope(narration_start_s=0.0, narration_end_s=10.0)
    lines = build_mix_filters(music_envelope=env, sfx_cues=(), sfx_input_labels={})
    assert any("volume=eval=frame" in line for line in lines)
    amix_line = lines[-1]
    assert "amix=inputs=2:normalize=0:duration=first[mix]" in amix_line
    assert "[0:a][music_env]" in amix_line


def test_build_mix_filters_adds_delayed_low_gain_sfx_inputs():
    env = DuckingEnvelope(narration_start_s=0.0, narration_end_s=10.0)
    cues = (SfxCue(tag="door_creak", offset_ms=850, word="puerta"),)
    lines = build_mix_filters(
        music_envelope=env, sfx_cues=cues, sfx_input_labels={"door_creak": "2:a"}, sfx_gain=0.032,
    )
    sfx_line = next(line for line in lines if line.startswith("[2:a]adelay="))
    assert "adelay=850|850" in sfx_line
    assert "volume=0.0320" in sfx_line
    assert sfx_line.endswith("[sfx0]")
    amix_line = lines[-1]
    assert "amix=inputs=3:normalize=0:duration=first[mix]" in amix_line
    assert "[sfx0]" in amix_line


def test_sfx_gain_is_distinctly_lower_than_typical_duck_gain():
    """The spec requires SFX to be genuinely quieter than the ducked music, not
    'also low' — assert the default relationship holds numerically."""
    env = DuckingEnvelope(narration_start_s=0.0, narration_end_s=10.0, duck_gain=0.1)
    cues = (SfxCue(tag="wind", offset_ms=0, word="viento"),)
    lines = build_mix_filters(
        music_envelope=env, sfx_cues=cues, sfx_input_labels={"wind": "2:a"},
    )
    sfx_line = next(line for line in lines if "adelay" in line)
    assert "volume=0.0320" in sfx_line  # ~-30dB
    assert 0.032 < env.duck_gain  # sfx clearly quieter than duck_gain (~-20dB)


def test_missing_sfx_asset_is_silently_skipped_not_an_error():
    env = DuckingEnvelope(narration_start_s=0.0, narration_end_s=10.0)
    cues = (SfxCue(tag="no_asset_for_this_tag", offset_ms=100, word="x"),)
    lines = build_mix_filters(music_envelope=env, sfx_cues=cues, sfx_input_labels={})
    amix_line = lines[-1]
    assert "amix=inputs=2:" in amix_line  # narration + music only, sfx skipped
