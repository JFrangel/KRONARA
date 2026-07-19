from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


KNOWN_TOOLS = {
    "trend.search",
    "rights.verify",
    "knowledge.retrieve",
    "story.concept",
    "story.blueprint",
    "story.draft",
    "story.evaluate",
    "originality.check",
    "voice.synthesize",
    "audio.verify",
    "video.render",
    "media.qc",
    "publication.publish",
    "metrics.read",
    "experiment.assign",
    "memory.propose",
    "research.plan",
    "evidence.build",
    "analytics.execute",
    "performance.diagnose",
    "virality.evaluate",
    "improvement.evaluate",
    "improvement.status",
    "rag.evaluate",
}


@dataclass(frozen=True)
class AgentManifest:
    agent_id: str
    role: str
    model_family: str
    fallback_families: tuple[str, ...]
    skills: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    max_steps: int
    max_tool_calls: int
    timeout_seconds: int


class AgentCatalog:
    def __init__(self, manifests: tuple[AgentManifest, ...]):
        self._manifests = {item.agent_id: item for item in manifests}
        if len(self._manifests) != len(manifests):
            raise ValueError("duplicate agent id")

    @classmethod
    def load(cls, directory: Path) -> "AgentCatalog":
        manifests: list[AgentManifest] = []
        for path in sorted(Path(directory).glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            manifests.append(
                AgentManifest(
                    agent_id=raw["agent_id"],
                    role=raw["role"],
                    model_family=raw["model_family"],
                    fallback_families=tuple(raw.get("fallback_families", ())),
                    skills=tuple(raw.get("skills", ())),
                    allowed_tools=tuple(raw.get("allowed_tools", ())),
                    max_steps=int(raw["limits"]["max_steps"]),
                    max_tool_calls=int(raw["limits"]["max_tool_calls"]),
                    timeout_seconds=int(raw["limits"]["timeout_seconds"]),
                )
            )
        if not manifests:
            raise ValueError(f"no agent manifests found in {directory}")
        return cls(tuple(manifests))

    @property
    def agent_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._manifests))

    def get(self, agent_id: str) -> AgentManifest:
        return self._manifests[agent_id]

    def unknown_tools(self) -> tuple[str, ...]:
        used = {tool for manifest in self._manifests.values() for tool in manifest.allowed_tools}
        return tuple(sorted(used - KNOWN_TOOLS))
