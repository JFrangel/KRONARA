from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kronara.prompt_stack import AgentNarrativeProfile, PersonaProfile


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
    "operations.status",
    "tools.timeline",
    "evidence.read",
    "memory.search",
    "model.evaluate",
    "embedding.evaluate",
    "training.dataset_card",
    "hook.plan",
    "story.package",
    "reddit.thread.fetch",
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

    @classmethod
    def load_narrative_profile(
        cls,
        agent_id: str,
        agents_dir: Path,
        personas_dir: Path,
    ) -> AgentNarrativeProfile | None:
        _, narrative = cls.load_runtime_profiles(agent_id, agents_dir, personas_dir)
        return narrative

    @classmethod
    def load_runtime_profiles(
        cls,
        agent_id: str,
        agents_dir: Path,
        personas_dir: Path,
    ) -> tuple[PersonaProfile | None, AgentNarrativeProfile | None]:
        catalog = cls.load(agents_dir)
        manifest = catalog.get(agent_id)
        persona_path = personas_dir / "kronara.v1.json"
        narrative_path = personas_dir / f"{manifest.agent_id}.v1.json"

        persona = None
        if persona_path.exists():
            persona_payload = json.loads(persona_path.read_text(encoding="utf-8"))
            persona = PersonaProfile.from_dict(persona_payload)

        narrative = None
        if narrative_path.exists():
            narrative_payload = json.loads(narrative_path.read_text(encoding="utf-8"))
            narrative = AgentNarrativeProfile.from_dict(narrative_payload)

        return persona, narrative
