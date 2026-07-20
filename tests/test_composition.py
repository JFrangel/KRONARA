import pytest

from kronara.composition import (
    Shot,
    VisualAsset,
    VisualTrackPlan,
    build_visual_track_plan,
    crossfade_offsets_ms,
    generated_source_ms,
    plan_shots_for_scene,
    stage_for_offset,
    tier_for_scene,
    xfade_chain,
    zoompan_filter,
)

STAGES = (
    ("hook", 5),
    ("minimum_context", 10),
    ("first_incident", 10),
    ("escalation", 20),
    ("point_of_no_return", 10),
    ("investigation", 15),
    ("revelation", 10),
    ("climax", 10),
    ("consequences", 7),
    ("emotional_close", 3),
)


def asset(id_="a1"):
    return VisualAsset(id_, "placeholder", f"/tmp/{id_}.png", 768, 1344)


# ---- stage_for_offset ----------------------------------------------------


def test_stage_for_offset_hits_each_stage_at_its_boundary():
    total = 100_000  # 100s -> 1% = 1000ms, matches STAGES percentages directly
    assert stage_for_offset(0, total, STAGES) == "hook"
    assert stage_for_offset(4_000, total, STAGES) == "hook"  # 4% < 5%
    assert stage_for_offset(5_000, total, STAGES) == "hook"  # exactly at boundary
    assert stage_for_offset(5_001, total, STAGES) == "minimum_context"
    assert stage_for_offset(14_999, total, STAGES) == "minimum_context"
    assert stage_for_offset(97_001, total, STAGES) == "emotional_close"
    assert stage_for_offset(100_000, total, STAGES) == "emotional_close"


def test_stage_for_offset_handles_zero_total_gracefully():
    assert stage_for_offset(0, 0, STAGES) == "hook"


# ---- tier_for_scene -------------------------------------------------------


def test_hook_scene_gets_premium_tier():
    # scene 0 of 10 equal scenes over 100s -> midpoint at 5s = 5% = hook boundary
    per_scene = (10_000,) * 10
    assert tier_for_scene(0, per_scene) == "premium"


def test_middle_context_scene_gets_fast_tier():
    per_scene = (10_000,) * 10
    # scene 2 (20-30s), midpoint 25s = 25% -> first_incident (not premium)
    assert tier_for_scene(2, per_scene) == "fast"


def test_climax_scene_gets_premium_tier():
    per_scene = (10_000,) * 10
    # scene 7 (70-80s), midpoint 75s = 75% -> revelation (a premium stage)
    assert tier_for_scene(7, per_scene) == "premium"


def test_last_scene_is_always_premium_regardless_of_stage_math():
    # Last scene's own timing would land in "consequences" (fast), but the
    # explicit last-scene override forces premium per the product requirement.
    per_scene = (10_000,) * 10
    assert tier_for_scene(9, per_scene, is_last_scene=True) == "premium"


def test_tier_ignores_scene_purpose_free_text_by_design():
    """The critical correctness point: tier assignment must work even when
    scene.purpose is unrelated free text (as it is in production), because
    tier_for_scene never reads scene.purpose at all — only position."""
    # No purpose parameter exists on tier_for_scene's signature; this test
    # documents that guarantee structurally rather than by inspection.
    import inspect

    assert "purpose" not in inspect.signature(tier_for_scene).parameters


# ---- plan_shots_for_scene --------------------------------------------------


def test_short_scene_becomes_a_single_shot():
    shots = plan_shots_for_scene("scn1", 4000, "fast", [asset()])
    assert len(shots) == 1
    assert shots[0].duration_ms == 4000


def test_long_scene_splits_into_multiple_shots_within_band():
    shots = plan_shots_for_scene("scn1", 20_000, "fast", [asset()])
    assert sum(s.duration_ms for s in shots) == 20_000
    for shot in shots:
        assert 3000 <= shot.duration_ms <= 7000 or len(shots) == 1


def test_shots_cycle_through_multiple_assets():
    assets = [asset("a1"), asset("a2"), asset("a3")]
    shots = plan_shots_for_scene("scn1", 21_000, "fast", assets)
    used = {shot.asset.asset_id for shot in shots}
    assert len(used) > 1  # cycles rather than repeating one asset the whole scene


def test_rejects_zero_duration_and_empty_assets():
    with pytest.raises(ValueError):
        plan_shots_for_scene("scn1", 0, "fast", [asset()])
    with pytest.raises(ValueError):
        plan_shots_for_scene("scn1", 5000, "fast", [])


# ---- motion_bias (V3: per-program visual identity) --------------------------


def test_default_motion_bias_matches_original_standard_calibration():
    shots = plan_shots_for_scene("scn1", 5000, "premium", [asset()])
    assert shots[0].zoom_end == pytest.approx(1.22)
    assert shots[0].pan == "diagonal"


def test_subtle_motion_bias_reduces_zoom_delta_versus_standard():
    subtle = plan_shots_for_scene("scn1", 5000, "premium", [asset()], motion_bias="subtle")
    standard = plan_shots_for_scene("scn1", 5000, "premium", [asset()], motion_bias="standard")
    assert (subtle[0].zoom_end - 1.0) < (standard[0].zoom_end - 1.0)


def test_dynamic_motion_bias_increases_zoom_delta_versus_standard():
    dynamic = plan_shots_for_scene("scn1", 5000, "premium", [asset()], motion_bias="dynamic")
    standard = plan_shots_for_scene("scn1", 5000, "premium", [asset()], motion_bias="standard")
    assert (dynamic[0].zoom_end - 1.0) > (standard[0].zoom_end - 1.0)


def test_subtle_motion_bias_prefers_slower_reading_pans():
    shots = plan_shots_for_scene("scn1", 5000, "fast", [asset()], motion_bias="subtle")
    assert shots[0].pan in {"center_in", "top_bottom"}


def test_unknown_motion_bias_raises():
    with pytest.raises(ValueError):
        plan_shots_for_scene("scn1", 5000, "fast", [asset()], motion_bias="chaotic")


# ---- Shot / VisualTrackPlan validation -------------------------------------


def test_shot_rejects_invalid_tier():
    with pytest.raises(ValueError):
        Shot("s1", "scn1", asset(), 5000, "ultra", 1.0, 1.2, "center_in")


def test_track_plan_rejects_mismatched_total():
    shots = (Shot("s1", "scn1", asset(), 5000, "fast", 1.0, 1.14, "center_in"),)
    with pytest.raises(ValueError):
        VisualTrackPlan(shots=shots, total_duration_ms=9999, crossfade_ms=400)


def test_build_visual_track_plan_sums_correctly():
    shots = plan_shots_for_scene("scn1", 20_000, "fast", [asset()])
    plan = build_visual_track_plan(shots, crossfade_ms=400)
    assert plan.total_duration_ms == 20_000
    assert sum(s.duration_ms for s in plan.shots) == plan.total_duration_ms


# ---- crossfade bookkeeping --------------------------------------------------


def _plan_from_durations(durations_ms, crossfade_ms=400):
    shots = tuple(
        Shot(f"s{i}", "scn1", asset(), d, "fast", 1.0, 1.14, "center_in")
        for i, d in enumerate(durations_ms)
    )
    return build_visual_track_plan(shots, crossfade_ms=crossfade_ms)


def test_generated_source_ms_pads_every_shot_except_the_last():
    plan = _plan_from_durations([5000, 6000, 4000], crossfade_ms=400)
    assert generated_source_ms(plan, 0) == 5000 + 400
    assert generated_source_ms(plan, 1) == 6000 + 400
    assert generated_source_ms(plan, 2) == 4000  # last shot: no trailing pad


def test_crossfade_offsets_are_cumulative_effective_durations():
    plan = _plan_from_durations([5000, 6000, 4000], crossfade_ms=400)
    assert crossfade_offsets_ms(plan) == (5000, 11000)


def test_single_shot_plan_has_no_crossfade_offsets():
    plan = _plan_from_durations([5000])
    assert crossfade_offsets_ms(plan) == ()


# ---- ffmpeg filter string construction --------------------------------------


def test_zoompan_filter_produces_exact_expected_substrings():
    shot = Shot("s1", "scn1", asset(), 5000, "fast", 1.0, 1.14, "center_in")
    filter_str = zoompan_filter(
        shot, label_in="0:v", label_out="v0", preset_width=1080, preset_height=1920,
        fps=30, source_ms=5000,
    )
    assert filter_str.startswith("[0:v]scale=3840:-1:flags=lanczos,")
    assert "zoompan=z='min(zoom+" in filter_str
    assert "d=150" in filter_str  # 5000ms * 30fps / 1000 = 150 frames
    assert "s=1080x1920:fps=30" in filter_str
    assert filter_str.endswith("[v0]")


def test_xfade_chain_hand_computed_offsets_for_three_shots():
    plan = _plan_from_durations([5000, 6000, 4000], crossfade_ms=400)
    lines = xfade_chain(plan, ["v0", "v1", "v2"])
    assert len(lines) == 2
    assert "offset=5.000" in lines[0]
    assert "duration=0.400" in lines[0]
    assert lines[0].startswith("[v0][v1]xfade=")
    assert lines[0].endswith("[vx1]")
    assert "offset=11.000" in lines[1]
    assert lines[1].startswith("[vx1][v2]xfade=")
    assert lines[1].endswith("[vout]")


def test_xfade_chain_two_shots_outputs_vout_directly():
    plan = _plan_from_durations([5000, 5000], crossfade_ms=400)
    lines = xfade_chain(plan, ["v0", "v1"])
    assert len(lines) == 1
    assert lines[0].endswith("[vout]")


def test_pan_expressions_differ_by_direction():
    left_right = Shot("s1", "scn1", asset(), 5000, "premium", 1.0, 1.22, "left_right")
    diagonal = Shot("s2", "scn1", asset(), 5000, "premium", 1.0, 1.22, "diagonal")
    lr_filter = zoompan_filter(left_right, label_in="0:v", label_out="v0",
                                preset_width=1080, preset_height=1920, fps=30, source_ms=5000)
    diag_filter = zoompan_filter(diagonal, label_in="0:v", label_out="v0",
                                  preset_width=1080, preset_height=1920, fps=30, source_ms=5000)
    assert lr_filter != diag_filter
    assert "*0.4" in diag_filter  # diagonal's characteristic vertical dampening
    assert "*0.4" not in lr_filter
