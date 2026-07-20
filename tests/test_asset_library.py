import pytest

from kronara.asset_library import AssetLibraryStore, LibraryAsset


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
