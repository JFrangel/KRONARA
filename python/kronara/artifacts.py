from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    path: Path
    size_bytes: int


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def put_bytes(self, content: bytes) -> ArtifactRef:
        digest = hashlib.sha256(content).hexdigest()
        path = self.root / digest[:2] / digest[2:4] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        return ArtifactRef(digest, path, len(content))

