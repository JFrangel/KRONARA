import pytest

from kronara.asset_library import AssetLibraryStore, LibraryAsset, sfx_paths_from_library
from kronara.audio_mix import DEFAULT_KEYWORD_SFX, DuckingEnvelope, SfxCue, build_mix_filters


def track(**overrides) -> LibraryAsset:
    payload = dict(
        asset_type="music",
        tags=("paranormal-tension",),
        file_path="/library/music/paranormal_01.mp3",
        duration_ms=120_000,
        rights_mode="cc0",
        attribution_text="",
        license_url="https://freepd.com/",
        source_url="https://freepd.com/dark.php",
        added_at=100,
    )
    payload.update(overrides)
    return LibraryAsset(**payload)


def store(tmp_path) -> AssetLibraryStore:
    return AssetLibraryStore(tmp_path / "assets.db").initialize()


# ---- seed --------------------------------------------------------------------


def test_seed_adds_a_new_asset_and_derives_an_id(tmp_path):
    lib = store(tmp_path)
    added = lib.seed(track())
    assert added is True
    assert lib.count() == 1
    lib.close()


def test_seed_is_idempotent_on_the_same_type_and_path(tmp_path):
    lib = store(tmp_path)
    lib.seed(track())
    added_again = lib.seed(track())  # same asset_type + file_path -> dedup
    assert added_again is False
    assert lib.count() == 1
    lib.close()


def test_seed_rejects_unknown_asset_type(tmp_path):
    lib = store(tmp_path)
    with pytest.raises(ValueError):
        lib.seed(track(asset_type="soundtrack"))
    lib.close()


def test_seed_rejects_missing_rights_mode(tmp_path):
    lib = store(tmp_path)
    with pytest.raises(ValueError):
        lib.seed(track(rights_mode=""))
    lib.close()


def test_seed_preserves_rights_metadata_on_read_back(tmp_path):
    lib = store(tmp_path)
    lib.seed(track(rights_mode="cc_by", attribution_text="Kevin MacLeod", license_url="https://x/license"))
    [found] = lib.by_tag("music", "paranormal-tension")
    assert found.rights_mode == "cc_by"
    assert found.attribution_text == "Kevin MacLeod"
    assert found.license_url == "https://x/license"
    lib.close()


# ---- by_tag --------------------------------------------------------------------


def test_by_tag_filters_by_asset_type_and_tag(tmp_path):
    lib = store(tmp_path)
    lib.seed(track())
    lib.seed(track(file_path="/library/sfx/door.wav", asset_type="sfx", tags=("door_creak",)))
    assert len(lib.by_tag("music", "paranormal-tension")) == 1
    assert len(lib.by_tag("sfx", "paranormal-tension")) == 0
    assert len(lib.by_tag("sfx", "door_creak")) == 1


def test_by_tag_matches_one_tag_among_several_on_the_same_asset(tmp_path):
    lib = store(tmp_path)
    lib.seed(track(tags=("misterio-investigativo", "dramatico-emocional")))
    assert len(lib.by_tag("music", "dramatico-emocional")) == 1
    lib.close()


def test_by_tag_does_not_partial_match_a_different_tag_with_shared_substring(tmp_path):
    """'confesion-intimo' must not match a query for 'confesion' or vice versa --
    the LIKE pattern is comma-delimited, not a raw substring search."""
    lib = store(tmp_path)
    lib.seed(track(tags=("confesion-intimo",)))
    assert len(lib.by_tag("music", "confesion")) == 0
    assert len(lib.by_tag("music", "confesion-intimo")) == 1
    lib.close()


def test_by_tag_rotates_least_used_first(tmp_path):
    lib = store(tmp_path)
    lib.seed(track(file_path="/a.mp3", added_at=100))
    lib.seed(track(file_path="/b.mp3", added_at=200))
    first_pick = lib.by_tag("music", "paranormal-tension", limit=1)[0]
    lib.mark_used(first_pick.asset_id)
    second_pick = lib.by_tag("music", "paranormal-tension", limit=1)[0]
    assert second_pick.asset_id != first_pick.asset_id  # rotates to the less-used one
    lib.close()


def test_mark_used_increments_use_count(tmp_path):
    lib = store(tmp_path)
    lib.seed(track())
    [found] = lib.by_tag("music", "paranormal-tension")
    assert found.use_count == 0
    lib.mark_used(found.asset_id)
    [found_again] = lib.by_tag("music", "paranormal-tension")
    assert found_again.use_count == 1
    lib.close()


def test_by_tag_respects_limit(tmp_path):
    lib = store(tmp_path)
    for i in range(5):
        lib.seed(track(file_path=f"/library/music/track{i}.mp3"))
    assert len(lib.by_tag("music", "paranormal-tension", limit=3)) == 3
    lib.close()


def sfx(**overrides) -> LibraryAsset:
    payload = dict(
        asset_type="sfx",
        tags=("door_creak",),
        file_path="/library/sfx/door_creak_01.wav",
        duration_ms=1200,
        rights_mode="cc0",
        source_url="https://freesound.org/",
        added_at=100,
    )
    payload.update(overrides)
    return LibraryAsset(**payload)


# ---- sfx_paths_from_library (V5: the AssetLibraryStore <-> render.py adapter) --


def test_sfx_paths_from_library_resolves_seeded_tags(tmp_path):
    lib = store(tmp_path)
    lib.seed(sfx())
    lib.seed(sfx(tags=("footsteps",), file_path="/library/sfx/footsteps_01.wav"))

    resolved = sfx_paths_from_library(lib, ["door_creak", "footsteps"])

    assert resolved == {
        "door_creak": "/library/sfx/door_creak_01.wav",
        "footsteps": "/library/sfx/footsteps_01.wav",
    }
    lib.close()


def test_sfx_paths_from_library_omits_unseeded_tags_without_erroring(tmp_path):
    lib = store(tmp_path)
    lib.seed(sfx())
    resolved = sfx_paths_from_library(lib, ["door_creak", "wind", "heartbeat"])
    assert resolved == {"door_creak": "/library/sfx/door_creak_01.wav"}
    lib.close()


def test_sfx_paths_from_library_marks_resolved_assets_used(tmp_path):
    lib = store(tmp_path)
    lib.seed(sfx())
    sfx_paths_from_library(lib, ["door_creak"])
    [found] = lib.by_tag("sfx", "door_creak")
    assert found.use_count == 1
    lib.close()


def test_sfx_paths_from_library_covers_every_default_keyword_tag(tmp_path):
    """Every tag DEFAULT_KEYWORD_SFX can produce must be resolvable once
    seeded -- this is the exact tag vocabulary V5's real Freesound curation
    needs to cover (door_creak, footsteps, wind, heartbeat, phone_ring,
    page_turn, static, whisper)."""
    lib = store(tmp_path)
    all_tags = sorted(set(DEFAULT_KEYWORD_SFX.values()))
    for tag in all_tags:
        lib.seed(sfx(tags=(tag,), file_path=f"/library/sfx/{tag}.wav"))
    resolved = sfx_paths_from_library(lib, all_tags)
    assert set(resolved.keys()) == set(all_tags)
    lib.close()


def test_full_chain_library_to_mix_filters(tmp_path):
    """End-to-end proof: seeded library -> sfx_paths_from_library ->
    build_mix_filters produces a real amix filter line referencing the
    library-resolved SFX input, not a hand-built dict."""
    lib = store(tmp_path)
    lib.seed(sfx(tags=("door_creak",), file_path="/library/sfx/door_creak_01.wav"))

    cues = (SfxCue(tag="door_creak", offset_ms=1050, word="puerta"),)
    sfx_paths = sfx_paths_from_library(lib, {cue.tag for cue in cues})
    sfx_input_labels = {tag: f"{2 + i}:a" for i, tag in enumerate(sfx_paths)}

    envelope = DuckingEnvelope(narration_start_s=0.0, narration_end_s=5.0)
    lines = build_mix_filters(
        music_envelope=envelope, sfx_cues=cues, sfx_input_labels=sfx_input_labels,
    )

    assert any("adelay=1050|1050" in line for line in lines)
    lib.close()
