from pathlib import Path

from kronara.asset_library import AssetLibraryStore
from kronara.freesound_harvest import harvest_freesound


def _library(tmp_path):
    return AssetLibraryStore(tmp_path / "assets.db").initialize()


def _hit(sound_id="42", seconds=6.0):
    return {"id": sound_id, "name": "Dark Drone", "license": "Creative Commons 0",
            "duration": seconds, "username": "composer", "url": f"https://freesound.org/s/{sound_id}/"}


def _fake_download(sound_id, dest_stem):
    path = Path(dest_stem).with_suffix(".wav")
    path.write_bytes(b"fake-wav")
    return str(path)


def test_harvest_seeds_cc0_music_with_attribution(tmp_path):
    library = _library(tmp_path)
    result = harvest_freesound(
        search=lambda q, lo, hi: _hit(),
        download=_fake_download,
        library=library,
        queries={"paranormal-tension": "dark tension drone"},
        asset_type="music",
        dest_dir=tmp_path / "music",
        min_duration=5.0,
        max_duration=90.0,
        now=1000,
    )
    assert result["seeded"] == 1
    asset = library.by_tag("music", "paranormal-tension")[0]
    assert asset.rights_mode == "cc0"
    assert asset.duration_ms == 6000
    assert "Freesound" in asset.attribution_text
    assert "creativecommons.org/publicdomain/zero" in asset.license_url
    assert Path(asset.file_path).is_file()


def test_harvest_is_idempotent_and_survives_missing_and_errors(tmp_path):
    library = _library(tmp_path)

    def search(query, lo, hi):
        if query == "gone":
            return None
        if query == "boom":
            raise RuntimeError("api down")
        return _hit("7", 4.0)

    queries = {"door_creak": "door creak", "silent": "gone", "broken": "boom"}
    # queries map tag->query; use query text as the switch.
    queries = {"door_creak": "present", "missing_tag": "gone", "err_tag": "boom"}
    first = harvest_freesound(
        search=search, download=_fake_download, library=library, queries=queries,
        asset_type="sfx", dest_dir=tmp_path / "sfx", min_duration=0.2, max_duration=8.0,
    )
    statuses = {r["tag"]: r["status"] for r in first["reports"]}
    assert statuses["door_creak"] == "seeded"
    assert statuses["missing_tag"] == "no_result"
    assert statuses["err_tag"] == "error"
    assert first["seeded"] == 1
    # Re-run: the seeded one dedups.
    second = harvest_freesound(
        search=search, download=_fake_download, library=library, queries=queries,
        asset_type="sfx", dest_dir=tmp_path / "sfx", min_duration=0.2, max_duration=8.0,
    )
    assert second["seeded"] == 0
    assert library.count("sfx") == 1
