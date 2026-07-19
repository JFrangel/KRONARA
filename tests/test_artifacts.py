from pathlib import Path

from kronara.artifacts import ArtifactStore


def test_artifact_store_is_content_addressed(tmp_path: Path):
    store = ArtifactStore(tmp_path)

    first = store.put_bytes(b"same content")
    second = store.put_bytes(b"same content")

    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert first.path.read_bytes() == b"same content"

