from pathlib import Path

from kronara.asset_library import AssetLibraryStore
from kronara.pexels_harvest import authority_search, harvest_video_loops, select_video


class FakeAuthority:
    def __init__(self, videos_by_query=None, default_videos=None):
        self.calls = []
        self._videos_by_query = videos_by_query or {}
        self._default = default_videos if default_videos is not None else []

    def invoke(self, tool_id, arguments):
        self.calls.append((tool_id, arguments))
        query = arguments["query"]
        return {"schema_version": 1, "videos": self._videos_by_query.get(query, self._default)}


def _video(source_id="v1", seconds=12):
    return {
        "source_id": source_id,
        "source_uri": f"https://www.pexels.com/video/{source_id}/",
        "download_url": f"https://cdn.pexels.com/{source_id}.mp4",
        "width": 720,
        "height": 1280,
        "duration_seconds": seconds,
        "photographer": "Jane Doe",
    }


def _library(tmp_path):
    return AssetLibraryStore(tmp_path / "assets.db").initialize()


def _fake_download(url, dest):
    Path(dest).write_bytes(b"fake-mp4-bytes")


def test_select_video_prefers_in_band_duration():
    chosen = select_video([_video("a", 120), _video("b", 11), _video("c", 3)])
    assert chosen["source_id"] == "b"


def test_select_video_none_without_download_url():
    assert select_video([{"source_id": "x", "duration_seconds": 10}]) is None
    assert select_video([]) is None


def test_harvest_seeds_a_video_loop_with_license(tmp_path):
    library = _library(tmp_path)
    authority = FakeAuthority(default_videos=[_video("v42", 10)])
    result = harvest_video_loops(
        search=authority_search(authority),
        library=library,
        tags=["night"],
        video_dir=tmp_path / "video_loop",
        download=_fake_download,
        now=1000,
    )
    assert result["seeded"] == 1
    assets = library.by_tag("video_loop", "night")
    assert len(assets) == 1
    asset = assets[0]
    assert asset.rights_mode == "pexels_license"
    assert asset.duration_ms == 10_000
    assert asset.license_url == "https://www.pexels.com/license/"
    assert Path(asset.file_path).is_file()
    assert Path(asset.file_path).parent == tmp_path / "video_loop"
    # The authority was asked with the portrait contract.
    tool, args = authority.calls[0]
    assert tool == "pexels.search_videos"
    assert args == {"schema_version": 1, "query": "night", "orientation": "portrait", "per_page": 5, "page": 1}


def test_harvest_is_idempotent_on_repeat(tmp_path):
    library = _library(tmp_path)
    authority = FakeAuthority(default_videos=[_video("same", 12)])
    kwargs = dict(
        search=authority_search(authority), library=library, tags=["night"],
        video_dir=tmp_path / "video_loop", download=_fake_download, now=1,
    )
    first = harvest_video_loops(**kwargs)
    second = harvest_video_loops(**kwargs)
    assert first["seeded"] == 1
    assert second["seeded"] == 0
    assert second["reports"][0]["status"] == "duplicate"
    assert library.count("video_loop") == 1


def test_harvest_reports_no_result_without_stopping_other_tags(tmp_path):
    library = _library(tmp_path)
    authority = FakeAuthority(videos_by_query={"city": [_video("c1", 9)]}, default_videos=[])
    result = harvest_video_loops(
        search=authority_search(authority),
        library=library,
        tags=["night", "city"],
        video_dir=tmp_path / "video_loop",
        download=_fake_download,
    )
    statuses = {r["tag"]: r["status"] for r in result["reports"]}
    assert statuses["night"] == "no_result"
    assert statuses["city"] == "seeded"
    assert result["seeded"] == 1


def test_harvest_never_calls_the_real_network(tmp_path):
    # The download callable is injected; assert it is the only thing invoked.
    library = _library(tmp_path)
    authority = FakeAuthority(default_videos=[_video("v", 10)])
    downloaded = []

    def spy_download(url, dest):
        downloaded.append(url)
        Path(dest).write_bytes(b"x")

    harvest_video_loops(
        search=authority_search(authority), library=library, tags=["night"],
        video_dir=tmp_path / "video_loop", download=spy_download,
    )
    assert downloaded == ["https://cdn.pexels.com/v.mp4"]
