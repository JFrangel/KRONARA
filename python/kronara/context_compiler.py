from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from kronara.context import ContextBuilder, TrustLevel


class ContextBudgetError(ValueError):
    pass


@dataclass(frozen=True)
class ContextRequest:
    policy: str
    max_tokens: int
    response_reserve_tokens: int
    required_topics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("max tokens must be positive")
        if not 0 <= self.response_reserve_tokens < self.max_tokens:
            raise ValueError("response reserve must be smaller than max tokens")


@dataclass(frozen=True)
class ContextFragment:
    item_id: str
    content: str
    citation_uri: str
    trust: TrustLevel
    priority: int = 0
    topic: str | None = None
    critical: bool = False


@dataclass(frozen=True)
class CompiledContext:
    policy: str
    context: str
    citations: tuple[str, ...]
    included_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    token_estimate: int
    coverage: float
    injection_warnings: tuple[str, ...]


class ContextCompiler:
    """Compiles cited context under an explicit model and response budget."""

    _TRUST_RANK = {
        TrustLevel.UNTRUSTED: 0,
        TrustLevel.INTERNAL: 1,
        TrustLevel.VERIFIED: 2,
    }

    def compile(
        self,
        request: ContextRequest,
        fragments: Iterable[ContextFragment],
    ) -> CompiledContext:
        source = tuple(fragments)
        unique, duplicate_ids = self._deduplicate(source)
        required = set(request.required_topics)
        ordered = sorted(
            unique,
            key=lambda item: (
                not item.critical,
                item.topic not in required,
                -self._TRUST_RANK[item.trust],
                -item.priority,
                item.item_id,
            ),
        )
        context_budget = request.max_tokens - request.response_reserve_tokens
        used = self.estimate_tokens(request.policy)
        if used > context_budget:
            raise ContextBudgetError("policy exceeds context budget")

        chunks: list[str] = []
        included: list[ContextFragment] = []
        omitted = list(duplicate_ids)
        warnings: list[str] = []
        for item in ordered:
            chunk = self._format(item)
            chunk_tokens = self.estimate_tokens(chunk)
            if used + chunk_tokens > context_budget:
                if item.critical:
                    raise ContextBudgetError(
                        f"critical evidence does not fit context budget: {item.item_id}"
                    )
                omitted.append(item.item_id)
                continue
            chunks.append(chunk)
            included.append(item)
            used += chunk_tokens
            if item.trust is TrustLevel.UNTRUSTED and ContextBuilder.detect_injection(
                item.content
            ):
                warnings.append(item.item_id)

        covered = {item.topic for item in included if item.topic in required}
        coverage = len(covered) / len(required) if required else 1.0
        return CompiledContext(
            policy=request.policy,
            context="\n\n".join(chunks),
            citations=tuple(item.citation_uri for item in included),
            included_ids=tuple(item.item_id for item in included),
            omitted_ids=tuple(sorted(set(omitted))),
            token_estimate=used,
            coverage=coverage,
            injection_warnings=tuple(warnings),
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text.encode("utf-8")) / 4))

    def _deduplicate(
        self, fragments: tuple[ContextFragment, ...]
    ) -> tuple[tuple[ContextFragment, ...], tuple[str, ...]]:
        by_content: dict[str, ContextFragment] = {}
        omitted: list[str] = []
        for item in fragments:
            normalized = " ".join(item.content.casefold().split())
            current = by_content.get(normalized)
            if current is None:
                by_content[normalized] = item
                continue
            winner = max(
                (current, item),
                key=lambda candidate: (
                    candidate.critical,
                    self._TRUST_RANK[candidate.trust],
                    candidate.priority,
                    candidate.item_id,
                ),
            )
            loser = item if winner is current else current
            by_content[normalized] = winner
            omitted.append(loser.item_id)
        return tuple(by_content.values()), tuple(omitted)

    @staticmethod
    def _format(item: ContextFragment) -> str:
        topic = f' topic="{item.topic}"' if item.topic else ""
        return (
            f'<source trust="{item.trust.value}" id="{item.item_id}"{topic} '
            f'citation="{item.citation_uri}">\n{item.content}\n</source>'
        )
