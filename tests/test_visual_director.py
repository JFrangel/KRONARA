import pytest

from kronara.asset_library import AssetLibraryStore, LibraryAsset
from kronara.composition import VisualAsset, plan_shots_for_scene
from kronara.visual_director import (
    GRAPHIC_OVERLAY_MAX_SHARE,
    VIDEO_LOOP_MAX_SHARE,
    assign_visual_sources,
    mentions_evidence,
)


def asset(id_="a1"):
    return VisualAsset(id_, "placeholder", f"/tmp/{id_}.png", 768, 1344)


def flat_shots(count, ms_each=4000):
    """`count` single-shot scenes (scn0..scnN-1), one shot per scene, so
    scene_texts can be keyed 1:1 against shots for a controlled fixture."""
    shots = []
    for i in range(count):
        shots.extend(plan_shots_for_scene(f"scn{i}", ms_each, "fast", [asset()]))
    return shots


def library_with_video_loop(tmp_path, tag="fog"):
    lib = AssetLibraryStore(tmp_path / "lib.db").initialize()
    lib.seed(
        LibraryAsset(
            asset_type="video_loop", tags=(tag,), file_path="/library/video/fog_01.mp4",
            duration_ms=6000, rights_mode="pexels_license", source_url="https://pexels.com/video/1",
            added_at=100,
        )
    )
    return lib


# ---- mentions_evidence -------------------------------------------------------


def test_mentions_evidence_true_for_keyword():
    assert mentions_evidence("Encontró un documento oculto en el cajón") is True


def test_mentions_evidence_false_without_keyword():
    assert mentions_evidence("Caminó despacio por el pasillo oscuro") is False


# ---- assign_visual_sources: defaults and fallbacks ---------------------------


def test_defaults_to_ai_image_with_no_signals(tmp_path):
    shots = flat_shots(5)
    assignments = assign_visual_sources(shots, scene_texts={})
    assert all(a.source_kind == "ai_image" for a in assignments)


def test_no_shot_is_left_without_a_source_kind(tmp_path):
    shots = flat_shots(10)
    texts = {f"scn{i}": "documento" if i % 2 == 0 else "" for i in range(10)}
    assignments = assign_visual_sources(shots, texts)
    assert all(a.source_kind in {"ai_image", "video_loop", "graphic_overlay"} for a in assignments)
    assert len(assignments) == len(shots)


# ---- graphic_overlay ---------------------------------------------------------


def test_evidence_keyword_triggers_graphic_overlay():
    shots = flat_shots(3)
    texts = {"scn0": "reviso el documento con cuidado", "scn1": "camina", "scn2": "silencio"}
    assignments = assign_visual_sources(shots, texts)
    assert assignments[0].source_kind == "graphic_overlay"
    assert assignments[1].source_kind == "ai_image"


def test_graphic_overlay_is_capped_even_with_abundant_evidence_signal():
    """If every single shot's narration mentions evidence, graphic_overlay
    must still not take over the episode -- it stays under its ceiling and
    the rest degrade to ai_image."""
    shots = flat_shots(30)
    texts = {f"scn{i}": "revisa el documento" for i in range(30)}

    assignments = assign_visual_sources(shots, texts)

    overlay_count = sum(1 for a in assignments if a.source_kind == "graphic_overlay")
    assert overlay_count / 30 <= GRAPHIC_OVERLAY_MAX_SHARE + 0.01  # small tolerance for rounding
    assert any(a.source_kind == "ai_image" for a in assignments)


# ---- video_loop ---------------------------------------------------------------


def test_video_loop_used_when_a_matching_asset_exists(tmp_path):
    shots = flat_shots(3)
    library = library_with_video_loop(tmp_path)
    assignments = assign_visual_sources(shots, {}, library=library, asset_tags=("fog",))
    assert assignments[0].source_kind == "video_loop"
    assert assignments[0].video_loop_asset.file_path == "/library/video/fog_01.mp4"
    library.close()


def test_video_loop_falls_back_to_ai_image_when_no_asset_matches(tmp_path):
    """The 'no toma queda sin recurso' guarantee: an empty library never
    raises, it just degrades to ai_image."""
    shots = flat_shots(3)
    library = AssetLibraryStore(tmp_path / "empty.db").initialize()
    assignments = assign_visual_sources(shots, {}, library=library, asset_tags=("fog",))
    assert all(a.source_kind == "ai_image" for a in assignments)
    library.close()


def test_video_loop_is_capped_even_with_abundant_matches(tmp_path):
    shots = flat_shots(30)
    library = library_with_video_loop(tmp_path)
    assignments = assign_visual_sources(shots, {}, library=library, asset_tags=("fog",))
    video_count = sum(1 for a in assignments if a.source_kind == "video_loop")
    assert video_count / 30 <= VIDEO_LOOP_MAX_SHARE + 0.01
    assert any(a.source_kind == "ai_image" for a in assignments)
    library.close()


def test_video_loop_dispensed_assets_are_marked_used(tmp_path):
    shots = flat_shots(3)
    library = library_with_video_loop(tmp_path)
    assign_visual_sources(shots, {}, library=library, asset_tags=("fog",))
    [found] = library.by_tag("video_loop", "fog")
    assert found.use_count >= 1
    library.close()


# ---- representative episode: the V6 acceptance criterion ---------------------


def test_representative_episode_lands_within_target_ranges(tmp_path):
    """On a realistic-shaped episode (some evidence beats, some available
    video-loop matches, the rest plain narrative), the final distribution
    across all three source kinds falls within the product spec's ranges:
    60-70% ai_image / 15-25% video_loop / 10-15% graphic_overlay."""
    shots = flat_shots(20)
    evidence_scenes = {0, 7, 14}
    video_scenes = {3, 6, 10, 13, 17}
    texts = {
        f"scn{i}": "revisa el documento" if i in evidence_scenes else "camina en silencio"
        for i in range(20)
    }
    library = library_with_video_loop(tmp_path)

    assignments = assign_visual_sources(shots, texts, library=library, asset_tags=("fog",))

    total = len(assignments)
    counts = {"ai_image": 0, "video_loop": 0, "graphic_overlay": 0}
    for a in assignments:
        counts[a.source_kind] += 1
    shares = {kind: count / total for kind, count in counts.items()}

    assert 0.60 <= shares["ai_image"] <= 0.70, shares
    assert 0.15 <= shares["video_loop"] <= 0.25, shares
    assert 0.10 <= shares["graphic_overlay"] <= 0.15, shares
    library.close()
