from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class TrustLevel(StrEnum):
    UNTRUSTED = "untrusted"
    INTERNAL = "internal"
    VERIFIED = "verified"


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    content: str
    citation_uri: str
    trust: TrustLevel
    priority: int = 0


@dataclass(frozen=True)
class ContextPackage:
    policy: str
    context: str
    citations: tuple[str, ...]
    injection_warnings: tuple[str, ...]


class ContextBuilder:
    """Builds a cited, budgeted context while preserving trust boundaries."""

    _INJECTION = re.compile(
        r"(?i)(ignore (all |the )?(previous|prior) instructions|system prompt|"
        r"developer message|override (the )?(rules|policy)|execute (this )?command|"
        r"publish this exact|ignora (las )?instrucciones (anteriores|previas)|"
        r"mensaje (del )?sistema|publica .* exactamente)"
    )

    def __init__(self, max_characters: int = 12_000):
        if max_characters < 1:
            raise ValueError("context budget must be positive")
        self.max_characters = max_characters

    @classmethod
    def detect_injection(cls, content: str) -> bool:
        return cls._INJECTION.search(content) is not None

    def build(self, policy: str, items: Iterable[ContextItem]) -> ContextPackage:
        chunks: list[str] = []
        citations: list[str] = []
        warnings: list[str] = []
        remaining = self.max_characters
        ordered = sorted(items, key=lambda item: (-item.priority, item.item_id))
        for item in ordered:
            if item.trust == TrustLevel.UNTRUSTED and self.detect_injection(item.content):
                warnings.append(item.item_id)
            chunk = (
                f'<source trust="{item.trust.value}" id="{item.item_id}" '
                f'citation="{item.citation_uri}">\n{item.content}\n</source>'
            )
            if len(chunk) > remaining:
                continue
            chunks.append(chunk)
            citations.append(item.citation_uri)
            remaining -= len(chunk)
        return ContextPackage(
            policy=policy,
            context="\n\n".join(chunks),
            citations=tuple(citations),
            injection_warnings=tuple(warnings),
        )
