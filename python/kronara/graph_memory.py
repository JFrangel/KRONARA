"""Bitemporal entity/relation knowledge graph for narrative continuity.

Kronara's RAG (``rag_v3``) already covers the *vector + lexical* half of a modern
hybrid memory. This module adds the missing *knowledge-graph* half: real entities
(characters, places, objects, topics, voices, programs, series) and typed
relations, with **valid-time** (when a fact holds in the story world) and
**transaction-time** (when Kronara learned it). That bitemporality is what lets a
serialized story remember its own canon across several videos.

No external graph engine is required: state lives in SQLite and traversal is a
plain BFS over an adjacency map, so the module installs and runs anywhere the
rest of the sidecar does.
"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

ENTITY_TYPES = frozenset(
    {"character", "place", "object", "topic", "voice", "program", "series", "fact"}
)

# ``valid_to = OPEN`` marks a fact that still holds ("until further notice").
OPEN = 1 << 62


@dataclass(frozen=True)
class GraphEntity:
    entity_id: str
    entity_type: str
    name: str
    series_id: str
    attributes: dict[str, str] = field(default_factory=dict)
    valid_from: int = 0
    valid_to: int = OPEN
    recorded_at: int = 0
    version: int = 1

    def __post_init__(self) -> None:
        if not self.entity_id or not self.name or not self.series_id:
            raise ValueError("entity requires id, name and series")
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unknown entity type: {self.entity_type}")
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")


@dataclass(frozen=True)
class GraphRelation:
    relation_id: str
    source_id: str
    relation: str
    target_id: str
    series_id: str
    weight: float = 1.0
    valid_from: int = 0
    valid_to: int = OPEN
    recorded_at: int = 0
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.relation_id, self.source_id, self.relation, self.target_id)):
            raise ValueError("relation requires id, source, relation and target")
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")


@dataclass(frozen=True)
class CanonSnapshot:
    series_id: str
    as_of: int
    entities: tuple[GraphEntity, ...]
    relations: tuple[GraphRelation, ...]

    def entity_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(entity.name for entity in self.entities))

    def facts(self) -> tuple[str, ...]:
        return tuple(
            entity.name for entity in self.entities if entity.entity_type == "fact"
        )


class KronaraGraph:
    """SQLite-backed bitemporal knowledge graph with in-memory traversal."""

    def __init__(self, database: Path | str):
        self.database = Path(database)
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> "KronaraGraph":
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = self._conn()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS kg_entities (
                entity_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                series_id TEXT NOT NULL,
                attributes TEXT NOT NULL,
                valid_from INTEGER NOT NULL,
                valid_to INTEGER NOT NULL,
                recorded_at INTEGER NOT NULL,
                PRIMARY KEY (entity_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_entities_series ON kg_entities(series_id);
            CREATE TABLE IF NOT EXISTS kg_relations (
                relation_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                target_id TEXT NOT NULL,
                series_id TEXT NOT NULL,
                weight REAL NOT NULL,
                valid_from INTEGER NOT NULL,
                valid_to INTEGER NOT NULL,
                recorded_at INTEGER NOT NULL,
                evidence TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_relations_series ON kg_relations(series_id);
            CREATE INDEX IF NOT EXISTS idx_relations_source ON kg_relations(source_id);
            """
        )
        connection.commit()
        return self

    # -- writes ---------------------------------------------------------------

    def upsert_entity(self, entity: GraphEntity) -> GraphEntity:
        """Insert an entity version. Re-inserting the same (id, version) is idempotent."""
        connection = self._conn()
        import json

        connection.execute(
            """
            INSERT INTO kg_entities
                (entity_id, version, entity_type, name, series_id, attributes,
                 valid_from, valid_to, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id, version) DO UPDATE SET
                entity_type=excluded.entity_type, name=excluded.name,
                series_id=excluded.series_id, attributes=excluded.attributes,
                valid_from=excluded.valid_from, valid_to=excluded.valid_to,
                recorded_at=excluded.recorded_at
            """,
            (
                entity.entity_id,
                entity.version,
                entity.entity_type,
                entity.name,
                entity.series_id,
                json.dumps(entity.attributes, ensure_ascii=False, sort_keys=True),
                entity.valid_from,
                entity.valid_to,
                entity.recorded_at,
            ),
        )
        connection.commit()
        return entity

    def supersede_entity(
        self, entity_id: str, replacement: GraphEntity, *, at: int
    ) -> GraphEntity:
        """Close the currently-open version of an entity and record a new one.

        This is how canon *changes* (a revealed truth) without erasing history:
        the prior version keeps its rows, bounded by ``valid_to = at``.
        """
        connection = self._conn()
        connection.execute(
            "UPDATE kg_entities SET valid_to=? WHERE entity_id=? AND valid_to>=?",
            (at, entity_id, at),
        )
        connection.commit()
        return self.upsert_entity(replacement)

    def add_relation(self, relation: GraphRelation) -> GraphRelation:
        connection = self._conn()
        import json

        connection.execute(
            """
            INSERT INTO kg_relations
                (relation_id, source_id, relation, target_id, series_id, weight,
                 valid_from, valid_to, recorded_at, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(relation_id) DO UPDATE SET
                source_id=excluded.source_id, relation=excluded.relation,
                target_id=excluded.target_id, series_id=excluded.series_id,
                weight=excluded.weight, valid_from=excluded.valid_from,
                valid_to=excluded.valid_to, recorded_at=excluded.recorded_at,
                evidence=excluded.evidence
            """,
            (
                relation.relation_id,
                relation.source_id,
                relation.relation,
                relation.target_id,
                relation.series_id,
                relation.weight,
                relation.valid_from,
                relation.valid_to,
                relation.recorded_at,
                json.dumps(list(relation.evidence_refs), ensure_ascii=False),
            ),
        )
        connection.commit()
        return relation

    # -- reads ----------------------------------------------------------------

    def entities(
        self,
        *,
        series_id: str | None = None,
        entity_type: str | None = None,
        as_of: int | None = None,
    ) -> tuple[GraphEntity, ...]:
        query = "SELECT * FROM kg_entities WHERE 1=1"
        params: list[object] = []
        if series_id is not None:
            query += " AND series_id=?"
            params.append(series_id)
        if entity_type is not None:
            query += " AND entity_type=?"
            params.append(entity_type)
        if as_of is not None:
            query += " AND valid_from<=? AND valid_to>?"
            params.extend((as_of, as_of))
        rows = self._conn().execute(query, params).fetchall()
        return tuple(self._entity(row) for row in rows)

    def relations(
        self, *, series_id: str | None = None, as_of: int | None = None
    ) -> tuple[GraphRelation, ...]:
        query = "SELECT * FROM kg_relations WHERE 1=1"
        params: list[object] = []
        if series_id is not None:
            query += " AND series_id=?"
            params.append(series_id)
        if as_of is not None:
            query += " AND valid_from<=? AND valid_to>?"
            params.extend((as_of, as_of))
        rows = self._conn().execute(query, params).fetchall()
        return tuple(self._relation(row) for row in rows)

    def neighbors(
        self, entity_id: str, *, as_of: int | None = None, max_hops: int = 2
    ) -> tuple[str, ...]:
        """BFS over relations (undirected) up to ``max_hops``; returns entity ids."""
        adjacency: dict[str, set[str]] = {}
        for relation in self.relations(as_of=as_of):
            adjacency.setdefault(relation.source_id, set()).add(relation.target_id)
            adjacency.setdefault(relation.target_id, set()).add(relation.source_id)
        seen = {entity_id}
        frontier: deque[tuple[str, int]] = deque([(entity_id, 0)])
        order: list[str] = []
        while frontier:
            current, depth = frontier.popleft()
            if depth >= max_hops:
                continue
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor not in seen:
                    seen.add(neighbor)
                    order.append(neighbor)
                    frontier.append((neighbor, depth + 1))
        return tuple(order)

    def canon(self, series_id: str, *, as_of: int | None = None) -> CanonSnapshot:
        """Everything true about a series at a point in time (its living canon)."""
        moment = OPEN - 1 if as_of is None else as_of
        return CanonSnapshot(
            series_id=series_id,
            as_of=moment,
            entities=self.entities(series_id=series_id, as_of=moment),
            relations=self.relations(series_id=series_id, as_of=moment),
        )

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    # -- internals ------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.database)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @staticmethod
    def _entity(row: sqlite3.Row) -> GraphEntity:
        import json

        return GraphEntity(
            entity_id=row["entity_id"],
            entity_type=row["entity_type"],
            name=row["name"],
            series_id=row["series_id"],
            attributes=json.loads(row["attributes"]),
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            recorded_at=row["recorded_at"],
            version=row["version"],
        )

    @staticmethod
    def _relation(row: sqlite3.Row) -> GraphRelation:
        import json

        return GraphRelation(
            relation_id=row["relation_id"],
            source_id=row["source_id"],
            relation=row["relation"],
            target_id=row["target_id"],
            series_id=row["series_id"],
            weight=row["weight"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            recorded_at=row["recorded_at"],
            evidence_refs=tuple(json.loads(row["evidence"])),
        )
