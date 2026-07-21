"""Per-program visual identity — style/negative prompts, motion character, and
asset-selection tags, loaded from ``config/programs/visual_style.v1.json``
(same registry pattern as ``EmbeddingRegistry``).

Keeps program identity distinguishable end to end: Viernes Paranormal reads
as fog and sickly green dread, Cronicas de Justicia reads as documentary
offices and evidence, without the image-generation or composition code
knowing anything about specific programs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kronara.resource_root import resource_root

MOTION_BIASES = frozenset({"subtle", "standard", "dynamic"})


@dataclass(frozen=True)
class VisualStyleDescriptor:
    program_id: str
    display_name: str
    weekday: str
    style_prompt: str
    negative_prompt: str
    motion_bias: str
    music_moods: tuple[str, ...]
    asset_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.program_id or not self.display_name:
            raise ValueError("visual style identity is required")
        if not self.style_prompt.strip():
            raise ValueError("style_prompt is required")
        if self.motion_bias not in MOTION_BIASES:
            raise ValueError(f"unknown motion_bias: {self.motion_bias}")


class VisualStyleRegistry:
    def __init__(self, descriptors: tuple[VisualStyleDescriptor, ...]):
        self._descriptors = {item.program_id: item for item in descriptors}
        if len(self._descriptors) != len(descriptors):
            raise ValueError("duplicate program_id")

    @classmethod
    def load(cls, path: Path) -> "VisualStyleRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported visual style registry schema")
        return cls(
            tuple(
                VisualStyleDescriptor(
                    program_id=str(item["program_id"]),
                    display_name=str(item["display_name"]),
                    weekday=str(item["weekday"]),
                    style_prompt=str(item["style_prompt"]),
                    negative_prompt=str(item.get("negative_prompt", "")),
                    motion_bias=str(item.get("motion_bias", "standard")),
                    music_moods=tuple(str(value) for value in item.get("music_moods", ())),
                    asset_tags=tuple(str(value) for value in item.get("asset_tags", ())),
                )
                for item in payload["programs"]
            )
        )

    def get(self, program_id: str) -> VisualStyleDescriptor:
        return self._descriptors[program_id]

    @property
    def program_ids(self) -> tuple[str, ...]:
        return tuple(self._descriptors.keys())


def default_registry_path() -> Path:
    return resource_root() / "config" / "programs" / "visual_style.v1.json"


def apply_style(
    base_prompt: str, base_negative_prompt: str, style: VisualStyleDescriptor | None
) -> tuple[str, str]:
    """Combine a shot's creative prompt with a program's visual identity. A
    ``None`` style (standalone stories with no program_id) returns the base
    prompts unchanged, so styling stays fully optional."""
    if style is None:
        return base_prompt, base_negative_prompt
    prompt = f"{base_prompt}, {style.style_prompt}" if base_prompt.strip() else style.style_prompt
    negatives = [text for text in (base_negative_prompt.strip(), style.negative_prompt.strip()) if text]
    return prompt, ", ".join(negatives)
