from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    version: int
    capabilities: tuple[str, ...]
    instruction_uri: str | None = None
    description: str = ""


class SkillRegistry:
    """Versioned capability registry that loads the minimum useful skill set."""

    def __init__(self, skills: Iterable[SkillSpec]):
        self._skills = tuple(skills)
        identities: set[tuple[str, int]] = set()
        for skill in self._skills:
            identity = (skill.skill_id, skill.version)
            if identity in identities:
                raise ValueError(f"duplicate skill: {skill.skill_id}@{skill.version}")
            identities.add(identity)

    @property
    def skills(self) -> tuple[SkillSpec, ...]:
        return self._skills

    def select(self, required_capabilities: Iterable[str]) -> tuple[SkillSpec, ...]:
        required = set(required_capabilities)
        if not required:
            return ()
        available = {item for skill in self._skills for item in skill.capabilities}
        missing = sorted(required - available)
        if missing:
            raise LookupError(f"unsupported capabilities: {', '.join(missing)}")
        for size in range(1, len(self._skills) + 1):
            for candidate in combinations(self._skills, size):
                covered = {item for skill in candidate for item in skill.capabilities}
                if required <= covered:
                    return tuple(candidate)
        raise LookupError("unsupported capabilities")
