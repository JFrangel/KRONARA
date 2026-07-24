from pathlib import Path

from kronara.i2v import FalWanI2VProvider


def _png(tmp_path):
    img = tmp_path / "scene.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake")
    return str(img)


def _provider(tmp_path, transport, **kw):
    prov = FalWanI2VProvider(
        api_key="k", poll_interval=0.0, transport=transport,
        download=lambda url, dest: Path(dest).write_bytes(b"mp4"), **kw,
    )
    prov._sleep = lambda _s: None
    return prov


def test_from_env_disabled_without_flag_or_key():
    assert FalWanI2VProvider.from_env({}) is None
    assert FalWanI2VProvider.from_env({"KRONARA_I2V_ENABLED": "1"}) is None  # no key
    assert FalWanI2VProvider.from_env({"KRONARA_FAL_KEY": "k"}) is None  # not enabled
    prov = FalWanI2VProvider.from_env({"KRONARA_I2V_ENABLED": "1", "KRONARA_FAL_KEY": "k"})
    assert isinstance(prov, FalWanI2VProvider)


def test_animate_happy_path_submits_polls_and_downloads(tmp_path):
    calls = []

    def transport(method, url, payload=None):
        calls.append((method, url))
        if method == "POST":
            assert payload["aspect_ratio"] == "9:16"
            assert payload["image_url"].startswith("data:image/png;base64,")
            assert payload["prompt"]
            return 200, {"request_id": "req1"}
        if url.endswith("/status"):
            return 200, {"status": "COMPLETED"}
        return 200, {"video": {"url": "https://cdn.fal/v.mp4"}}

    prov = _provider(tmp_path, transport)
    out = prov.animate(image_path=_png(tmp_path), prompt="cámara lenta hacia el faro", dest=str(tmp_path / "clip.mp4"))
    assert out == str(tmp_path / "clip.mp4")
    assert Path(out).read_bytes() == b"mp4"
    assert calls[0][0] == "POST"


def test_animate_returns_none_on_submit_error(tmp_path):
    prov = _provider(tmp_path, lambda m, u, p=None: (401, {"error": "bad key"}))
    assert prov.animate(image_path=_png(tmp_path), prompt="x", dest=str(tmp_path / "c.mp4")) is None


def test_animate_returns_none_when_job_fails(tmp_path):
    def transport(method, url, payload=None):
        if method == "POST":
            return 200, {"request_id": "r"}
        return 200, {"status": "FAILED"}

    prov = _provider(tmp_path, transport)
    assert prov.animate(image_path=_png(tmp_path), prompt="x", dest=str(tmp_path / "c.mp4")) is None


def test_animate_times_out_without_completion(tmp_path):
    def transport(method, url, payload=None):
        if method == "POST":
            return 200, {"request_id": "r"}
        return 200, {"status": "IN_PROGRESS"}

    prov = _provider(tmp_path, transport, max_polls=3)
    assert prov.animate(image_path=_png(tmp_path), prompt="x", dest=str(tmp_path / "c.mp4")) is None
