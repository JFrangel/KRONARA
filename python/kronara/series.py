"""Serialized multi-part stories with shared canon.

A single story can span several videos (see ``knowledge/narrative/serialization.md``).
For that to hold together, Part N must know the characters, facts and open threads
established in Parts 1..N-1. This module turns a finished story run into durable
canon in the :class:`~kronara.graph_memory.KronaraGraph` and rebuilds the context
a later part needs.

Entity ids are deterministic (``series:character:<slug>``), so re-appearing
characters resolve to the *same* graph node across parts instead of duplicating.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from kronara.graph_memory import GraphEntity, GraphRelation, KronaraGraph, OPEN


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
    return text or hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


@dataclass(frozen=True)
class StoryPart:
    series_id: str
    part_number: int
    story_id: str
    cliffhanger: str = ""
    is_final: bool = False

    def __post_init__(self) -> None:
        if not self.series_id or not self.story_id:
            raise ValueError("a story part requires a series and a story id")
        if self.part_number < 1:
            raise ValueError("part_number starts at 1")
        # Every part except the last should end on an open question (cliffhanger).
        if not self.is_final and not self.cliffhanger.strip():
            raise ValueError("non-final parts must end on a cliffhanger")


@dataclass(frozen=True)
class SeriesContext:
    series_id: str
    next_part: int
    established_characters: tuple[str, ...]
    established_facts: tuple[str, ...]
    open_threads: tuple[str, ...]
    context_block: str

    def is_empty(self) -> bool:
        return not (self.established_characters or self.established_facts)


class SeriesCanonBuilder:
    """Writes a part's canon into the graph and reconstructs it for the next part."""

    def __init__(self, graph: KronaraGraph):
        self.graph = graph

    def ingest(
        self,
        part: StoryPart,
        *,
        characters: tuple[str, ...],
        facts: tuple[str, ...],
        now: int,
        evidence_refs: tuple[str, ...] = (),
    ) -> int:
        """Persist characters, facts and the part's open thread as canon.

        Returns the number of graph nodes written. Idempotent per (series, name):
        the same character across parts updates one node rather than duplicating.
        """
        written = 0
        for name in dict.fromkeys(characters):
            entity_id = f"{part.series_id}:character:{_slug(name)}"
            self.graph.upsert_entity(
                GraphEntity(
                    entity_id=entity_id,
                    entity_type="character",
                    name=name,
                    series_id=part.series_id,
                    attributes={"introduced_part": str(part.part_number)},
                    valid_from=now,
                    valid_to=OPEN,
                    recorded_at=now,
                )
            )
            written += 1
        for fact in dict.fromkeys(facts):
            entity_id = f"{part.series_id}:fact:{hashlib.sha256(fact.encode()).hexdigest()[:12]}"
            self.graph.upsert_entity(
                GraphEntity(
                    entity_id=entity_id,
                    entity_type="fact",
                    name=fact,
                    series_id=part.series_id,
                    attributes={"part": str(part.part_number)},
                    valid_from=now,
                    valid_to=OPEN,
                    recorded_at=now,
                )
            )
            written += 1
        # The cliffhanger is the open thread the next part must answer.
        if part.cliffhanger.strip():
            thread_id = f"{part.series_id}:fact:thread-{part.part_number}"
            self.graph.upsert_entity(
                GraphEntity(
                    entity_id=thread_id,
                    entity_type="fact",
                    name=part.cliffhanger.strip(),
                    series_id=part.series_id,
                    attributes={"kind": "open_thread", "part": str(part.part_number)},
                    valid_from=now,
                    valid_to=OPEN,
                    recorded_at=now,
                )
            )
            written += 1
            for name in dict.fromkeys(characters):
                self.graph.add_relation(
                    GraphRelation(
                        relation_id=f"{thread_id}:involves:{_slug(name)}",
                        source_id=thread_id,
                        relation="involves",
                        target_id=f"{part.series_id}:character:{_slug(name)}",
                        series_id=part.series_id,
                        valid_from=now,
                        valid_to=OPEN,
                        recorded_at=now,
                        evidence_refs=evidence_refs,
                    )
                )
        return written

    def ingest_story_result(
        self,
        series_id: str,
        part_number: int,
        result: object,
        *,
        now: int,
        cliffhanger: str = "",
        is_final: bool = False,
    ) -> StoryPart:
        """Convenience: pull characters/facts from a StoryEngine ``StoryRunResult``."""
        scenes = getattr(result, "scenes", ()) or ()
        characters = tuple(
            dict.fromkeys(
                character
                for scene in scenes
                for character in getattr(scene, "characters", ())
            )
        )
        continuity = getattr(result, "continuity", None)
        facts = tuple(getattr(continuity, "facts", ()) or ())
        story_id = getattr(result, "run_id", f"{series_id}:part:{part_number}")
        part = StoryPart(
            series_id=series_id,
            part_number=part_number,
            story_id=story_id,
            cliffhanger=cliffhanger,
            is_final=is_final,
        )
        self.ingest(part, characters=characters, facts=facts, now=now)
        return part

    def context_for_part(
        self, series_id: str, next_part: int, *, now: int
    ) -> SeriesContext:
        """Rebuild the canon a later part needs, as data and as a promptable block."""
        canon = self.graph.canon(series_id, as_of=now)
        characters = tuple(e.name for e in canon.entities if e.entity_type == "character")
        open_threads = tuple(
            e.name
            for e in canon.entities
            if e.entity_type == "fact" and e.attributes.get("kind") == "open_thread"
        )
        facts = tuple(
            e.name
            for e in canon.entities
            if e.entity_type == "fact" and e.attributes.get("kind") != "open_thread"
        )
        block = self._render_block(next_part, characters, facts, open_threads)
        return SeriesContext(
            series_id=series_id,
            next_part=next_part,
            established_characters=characters,
            established_facts=facts,
            open_threads=open_threads,
            context_block=block,
        )

    @staticmethod
    def _render_block(
        next_part: int,
        characters: tuple[str, ...],
        facts: tuple[str, ...],
        open_threads: tuple[str, ...],
    ) -> str:
        if not (characters or facts or open_threads):
            return ""
        lines = [f"CANON DE LA SERIE (para la parte {next_part}; respétalo, no lo contradigas):"]
        if characters:
            lines.append("Personajes establecidos: " + ", ".join(characters) + ".")
        if facts:
            lines.append("Hechos ya revelados:")
            lines.extend(f"- {fact}" for fact in facts)
        if open_threads:
            lines.append("Preguntas abiertas que esta parte debe retomar:")
            lines.extend(f"- {thread}" for thread in open_threads)
        return "\n".join(lines)
