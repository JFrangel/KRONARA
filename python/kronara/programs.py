"""Program registry -- config/programs/programs.v1.json.

v1: static metadata only (name, weekday, genre, target duration, visual
style/platform linkage). B1 (Agent B) extends this into full ScheduleRule
derivation later; this is deliberately the minimal slice the frontend (U3)
needs now, not a preview of B1's scheduler wiring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProgramDescriptor:
    program_id: str
    name: str
    weekday: str
    genre: str
    description: str
    visual_style_id: str
    target_duration_seconds: int
    platforms: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.program_id or not self.name:
            raise ValueError("program identity is required")
        if self.target_duration_seconds < 30:
            raise ValueError("program target duration must be at least thirty seconds")


class ProgramRegistry:
    def __init__(self, descriptors: tuple[ProgramDescriptor, ...]):
        self._descriptors = {item.program_id: item for item in descriptors}
        if len(self._descriptors) != len(descriptors):
            raise ValueError("duplicate program_id")

    @classmethod
    def load(cls, path: Path) -> "ProgramRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported program registry schema")
        return cls(
            tuple(
                ProgramDescriptor(
                    program_id=str(item["program_id"]),
                    name=str(item["name"]),
                    weekday=str(item["weekday"]),
                    genre=str(item["genre"]),
                    description=str(item.get("description", "")),
                    visual_style_id=str(item.get("visual_style_id", item["program_id"])),
                    target_duration_seconds=int(item["target_duration_seconds"]),
                    platforms=tuple(str(value) for value in item.get("platforms", ())),
                )
                for item in payload["programs"]
            )
        )

    def get(self, program_id: str) -> ProgramDescriptor:
        return self._descriptors[program_id]

    @property
    def program_ids(self) -> tuple[str, ...]:
        return tuple(self._descriptors.keys())

    def by_weekday(self, weekday: str) -> ProgramDescriptor | None:
        for descriptor in self._descriptors.values():
            if descriptor.weekday == weekday:
                return descriptor
        return None


def default_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "programs" / "programs.v1.json"
