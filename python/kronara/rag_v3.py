from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol, Sequence

import sqlite_vec

from kronara.embedding_registry import EmbeddingModelDescriptor
from kronara.intelligence import reciprocal_rank_fusion
from kronara.rag_v2 import Embedder, HierarchicalChunker, IngestDocument, KnowledgeChunk


class EmbeddingCompatibilityError(ValueError):
    pass


class Reranker(Protocol):
    def score(self, query: str, chunk: KnowledgeChunk) -> float: ...


@dataclass(frozen=True)
class RetrievalQueryV3:
    text: str
    now: int
    language: str | None = None
    scope: str | None = None
    allowed_rights: tuple[str, ...] = (
        "owned_original",
        "licensed_adaptation",
        "promoted_learning",
    )
    allowed_relations: tuple[str, ...] = (
        "related",
        "supports",
        "contradicts",
        "derived_from",
        "same_topic",
    )
    graph_depth: int = 1
    limit: int = 8
    max_per_document: int = 2
    maximum_subqueries: int = 4

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("retrieval query text is required")
        if not 0 <= self.graph_depth <= 3:
            raise ValueError("graph depth must be between zero and three")
        if not 1 <= self.limit <= 50:
            raise ValueError("retrieval limit must be between one and fifty")
        if not 1 <= self.max_per_document <= 10:
            raise ValueError("per-document limit must be between one and ten")
        if not 1 <= self.maximum_subqueries <= 4:
            raise ValueError("maximum subqueries must be between one and four")


@dataclass(frozen=True)
class RetrievalResultV3:
    chunk_id: str
    document_id: str
    section_path: tuple[str, ...]
    content: str
    rights_mode: str
    score: float
    confidence: float
    citation_uri: str


@dataclass(frozen=True)
class RetrievalPacketV3:
    query_class: str
    subqueries: tuple[str, ...]
    results: tuple[RetrievalResultV3, ...]
    stage_counts: dict[str, int]
    degradations: tuple[str, ...]
    index_id: str


@dataclass(frozen=True)
class RetrievalEvaluationCaseV2:
    query: str
    relevant_document_ids: tuple[str, ...]
    domain: str


@dataclass(frozen=True)
class RetrievalEvaluationV2:
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_precision: float
    redundancy_rate: float
    cases: int


class QueryDecomposer:
    _SEPARATORS = re.compile(r"\s+(?:y|o|versus|vs\.?|además|también)\s+|[?;]+", re.I)

    def decompose(self, text: str, maximum: int) -> tuple[str, ...]:
        normalized = " ".join(text.split())
        pieces = [piece.strip(" .,¿?") for piece in self._SEPARATORS.split(normalized)]
        unique = tuple(dict.fromkeys(piece for piece in pieces if len(piece) >= 3))
        return unique[:maximum] or (normalized,)

    @staticmethod
    def classify(text: str) -> str:
        normalized = text.casefold()
        if any(term in normalized for term in ("derecho", "licencia", "permiso")):
            return "rights"
        if any(term in normalized for term in ("métrica", "retención", "rendimiento")):
            return "performance"
        if any(term in normalized for term in ("contradic", "evidencia", "fuente")):
            return "research"
        return "editorial"


class RAGV3Index:
    """Persistent FTS5 + sqlite-vec + typed graph retrieval with rights-first filtering."""

    def __init__(
        self,
        database: Path,
        descriptor: EmbeddingModelDescriptor,
        embedder: Embedder,
        *,
        reranker: Reranker | None = None,
        chunker: HierarchicalChunker | None = None,
        decomposer: QueryDecomposer | None = None,
    ):
        if descriptor.kind != "embedding":
            raise EmbeddingCompatibilityError("descriptor is not an embedding model")
        if int(getattr(embedder, "dimensions", -1)) != descriptor.dimensions:
            raise EmbeddingCompatibilityError("embedder dimensions do not match descriptor")
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.descriptor = descriptor
        self.embedder = embedder
        self.reranker = reranker
        self.chunker = chunker or HierarchicalChunker()
        self.decomposer = decomposer or QueryDecomposer()
        self.connection = sqlite3.connect(self.database, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._vector_available = True
        self._vector_table = self._safe_vector_table(descriptor.version_hash)
        self._initialize()

    @property
    def index_id(self) -> str:
        return f"ragv3:{self.descriptor.alias}:{self.descriptor.version_hash}"

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS knowledge_documents_v3 (
                document_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                rights_mode TEXT NOT NULL,
                language TEXT NOT NULL,
                scope TEXT NOT NULL,
                valid_from INTEGER NOT NULL,
                valid_until INTEGER,
                confidence REAL NOT NULL,
                version INTEGER NOT NULL,
                tombstoned INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS knowledge_chunks_v3 (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                section_path_json TEXT NOT NULL,
                content TEXT NOT NULL,
                rights_mode TEXT NOT NULL,
                language TEXT NOT NULL,
                scope TEXT NOT NULL,
                valid_from INTEGER NOT NULL,
                valid_until INTEGER,
                confidence REAL NOT NULL,
                version INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_v3_document
                ON knowledge_chunks_v3(document_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                content,
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TABLE IF NOT EXISTS knowledge_edges_v3 (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY(source_id, target_id, relation)
            );
            CREATE TABLE IF NOT EXISTS embedding_index_manifests (
                index_id TEXT PRIMARY KEY,
                model_alias TEXT NOT NULL,
                version_hash TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS promoted_story_evidence_v3 (
                story_id TEXT PRIMARY KEY,
                evidence_refs_json TEXT NOT NULL,
                promoted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        try:
            self.connection.enable_load_extension(True)
            sqlite_vec.load(self.connection)
            self.connection.enable_load_extension(False)
            self.connection.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self._vector_table} USING vec0(
                    chunk_id TEXT PRIMARY KEY,
                    embedding FLOAT[{self.descriptor.dimensions}]
                )
                """
            )
            self.connection.execute(
                """
                INSERT INTO embedding_index_manifests(
                    index_id, model_alias, version_hash, dimensions, status
                ) VALUES (?, ?, ?, ?, 'active')
                ON CONFLICT(index_id) DO UPDATE SET status='active'
                """,
                (
                    self.index_id,
                    self.descriptor.alias,
                    self.descriptor.version_hash,
                    self.descriptor.dimensions,
                ),
            )
        except (sqlite3.Error, OSError):
            self._vector_available = False
            self.connection.execute(
                """
                INSERT INTO embedding_index_manifests(
                    index_id, model_alias, version_hash, dimensions, status
                ) VALUES (?, ?, ?, ?, 'degraded')
                ON CONFLICT(index_id) DO UPDATE SET status='degraded'
                """,
                (
                    self.index_id,
                    self.descriptor.alias,
                    self.descriptor.version_hash,
                    self.descriptor.dimensions,
                ),
            )
        self.connection.commit()

    def upsert(
        self,
        document: IngestDocument,
        *,
        vectors: Sequence[Sequence[float]] | None = None,
    ) -> tuple[KnowledgeChunk, ...]:
        chunks = self.chunker.chunk(document)
        if vectors is None:
            generated = [self.embedder.embed(chunk.content) for chunk in chunks]
        else:
            generated = [list(vector) for vector in vectors]
        if len(generated) != len(chunks):
            raise EmbeddingCompatibilityError("one vector is required for each chunk")
        if any(len(vector) != self.descriptor.dimensions for vector in generated):
            raise EmbeddingCompatibilityError("vector dimensions do not match index")
        existing = [
            row[0]
            for row in self.connection.execute(
                "SELECT chunk_id FROM knowledge_chunks_v3 WHERE document_id = ?",
                (document.document_id,),
            )
        ]
        for chunk_id in existing:
            self.connection.execute(
                "DELETE FROM knowledge_chunks_fts WHERE chunk_id = ?", (chunk_id,)
            )
            if self._vector_available:
                self.connection.execute(
                    f"DELETE FROM {self._vector_table} WHERE chunk_id = ?", (chunk_id,)
                )
        self.connection.execute(
            "DELETE FROM knowledge_chunks_v3 WHERE document_id = ?", (document.document_id,)
        )
        self.connection.execute(
            """
            INSERT INTO knowledge_documents_v3(
                document_id, title, rights_mode, language, scope, valid_from,
                valid_until, confidence, version, tombstoned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(document_id) DO UPDATE SET
                title=excluded.title,
                rights_mode=excluded.rights_mode,
                language=excluded.language,
                scope=excluded.scope,
                valid_from=excluded.valid_from,
                valid_until=excluded.valid_until,
                confidence=excluded.confidence,
                version=excluded.version,
                tombstoned=0
            """,
            (
                document.document_id,
                document.title,
                document.rights_mode,
                document.language,
                document.scope,
                document.valid_from,
                document.valid_until,
                document.confidence,
                document.version,
            ),
        )
        for chunk, vector in zip(chunks, generated):
            self.connection.execute(
                """
                INSERT INTO knowledge_chunks_v3(
                    chunk_id, document_id, section_path_json, content, rights_mode,
                    language, scope, valid_from, valid_until, confidence, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    json.dumps(chunk.section_path, ensure_ascii=False),
                    chunk.content,
                    chunk.rights_mode,
                    chunk.language,
                    chunk.scope,
                    chunk.valid_from,
                    chunk.valid_until,
                    chunk.confidence,
                    chunk.version,
                ),
            )
            self.connection.execute(
                "INSERT INTO knowledge_chunks_fts(chunk_id, document_id, content) VALUES (?, ?, ?)",
                (chunk.chunk_id, chunk.document_id, chunk.content),
            )
            if self._vector_available:
                self.connection.execute(
                    f"INSERT INTO {self._vector_table}(chunk_id, embedding) VALUES (?, ?)",
                    (chunk.chunk_id, sqlite_vec.serialize_float32(list(vector))),
                )
        self.connection.commit()
        return chunks

    def link_documents(
        self, source_id: str, target_id: str, relation: str, weight: float = 1.0
    ) -> None:
        if not source_id or not target_id or not relation or not 0 <= weight <= 1:
            raise ValueError("invalid knowledge edge")
        self.connection.execute(
            """
            INSERT INTO knowledge_edges_v3(source_id, target_id, relation, weight)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation) DO UPDATE SET weight=excluded.weight
            """,
            (source_id, target_id, relation, weight),
        )
        self.connection.commit()

    def promote_owned_story(
        self,
        story_id: str,
        content: str,
        evidence_refs: tuple[str, ...],
    ) -> None:
        if not story_id.strip() or not content.strip() or not evidence_refs:
            raise ValueError("owned story promotion requires identity, content and evidence")
        if any(not item.strip() for item in evidence_refs):
            raise ValueError("owned story promotion evidence cannot be empty")
        row = self.connection.execute(
            "SELECT version FROM knowledge_documents_v3 WHERE document_id = ?",
            (story_id,),
        ).fetchone()
        version = int(row["version"]) + 1 if row is not None else 1
        self.upsert(
            IngestDocument(
                document_id=story_id,
                title=f"Historia propia promovida {story_id}",
                content=content.strip(),
                rights_mode="promoted_learning",
                language="es",
                scope="narrative",
                valid_from=0,
                valid_until=None,
                confidence=0.9,
                version=version,
            )
        )
        self.connection.execute(
            """
            INSERT INTO promoted_story_evidence_v3(story_id, evidence_refs_json)
            VALUES (?, ?)
            ON CONFLICT(story_id) DO UPDATE SET
                evidence_refs_json=excluded.evidence_refs_json,
                promoted_at=CURRENT_TIMESTAMP
            """,
            (story_id, json.dumps(evidence_refs, ensure_ascii=False)),
        )
        self.connection.commit()

    def promotion_evidence(self, story_id: str) -> tuple[str, ...]:
        row = self.connection.execute(
            "SELECT evidence_refs_json FROM promoted_story_evidence_v3 WHERE story_id = ?",
            (story_id,),
        ).fetchone()
        if row is None:
            return ()
        return tuple(str(item) for item in json.loads(row["evidence_refs_json"]))

    def tombstone(self, document_id: str) -> None:
        self.connection.execute(
            "UPDATE knowledge_documents_v3 SET tombstoned = 1 WHERE document_id = ?",
            (document_id,),
        )
        self.connection.commit()

    def retrieve(self, query: RetrievalQueryV3) -> RetrievalPacketV3:
        subqueries = self.decomposer.decompose(query.text, query.maximum_subqueries)
        query_class = self.decomposer.classify(query.text)
        eligible = self._eligible_chunks(query)
        eligible_ids = set(eligible)
        lexical_ids = self._lexical(subqueries, eligible_ids)
        degradations: list[str] = []
        vector_ids: list[str] = []
        if self._vector_available and eligible_ids:
            try:
                vector_ids = self._vector(query.text, eligible_ids, query.limit * 10)
            except (RuntimeError, ValueError, sqlite3.Error):
                degradations.append("vector_unavailable")
        elif eligible_ids:
            degradations.append("vector_unavailable")
        graph_ids = self._graph(
            tuple(dict.fromkeys((*lexical_ids[:3], *vector_ids[:3]))),
            eligible,
            query.allowed_relations,
            query.graph_depth,
        )
        fused = reciprocal_rank_fusion((lexical_ids, vector_ids, graph_ids))
        fused_ids = [item.item_id for item in fused if item.item_id in eligible_ids]
        fused_scores = {item.item_id: item.score for item in fused}
        reranked_ids = list(fused_ids)
        if self.reranker is not None:
            try:
                reranked_ids.sort(
                    key=lambda chunk_id: (
                        -self.reranker.score(query.text, eligible[chunk_id]),
                        -fused_scores.get(chunk_id, 0.0),
                        chunk_id,
                    )
                )
            except Exception:
                degradations.append("reranker_unavailable")
                reranked_ids = list(fused_ids)
        deduplicated_ids = self._semantic_deduplicate(reranked_ids, eligible)
        selected_ids = self._diversify(
            deduplicated_ids, eligible, query.limit, query.max_per_document
        )
        results = tuple(
            RetrievalResultV3(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                section_path=chunk.section_path,
                content=chunk.content,
                rights_mode=chunk.rights_mode,
                score=fused_scores.get(chunk.chunk_id, 0.0) * chunk.confidence,
                confidence=chunk.confidence,
                citation_uri=f"kronara://knowledge/{chunk.document_id}/{chunk.chunk_id}",
            )
            for chunk in (eligible[chunk_id] for chunk_id in selected_ids)
        )
        return RetrievalPacketV3(
            query_class=query_class,
            subqueries=subqueries,
            results=results,
            stage_counts={
                "eligible": len(eligible),
                "lexical": len(lexical_ids),
                "vector": len(vector_ids),
                "graph": len(graph_ids),
                "fused": len(fused_ids),
                "reranked": len(reranked_ids),
                "deduplicated": len(deduplicated_ids),
                "selected": len(selected_ids),
            },
            degradations=tuple(dict.fromkeys(degradations)),
            index_id=self.index_id,
        )

    def _eligible_chunks(self, query: RetrievalQueryV3) -> dict[str, KnowledgeChunk]:
        rows = self.connection.execute(
            """
            SELECT c.* FROM knowledge_chunks_v3 c
            JOIN knowledge_documents_v3 d ON d.document_id = c.document_id
            WHERE d.tombstoned = 0
            """
        )
        eligible: dict[str, KnowledgeChunk] = {}
        for row in rows:
            if row["rights_mode"] not in query.allowed_rights:
                continue
            if query.language is not None and row["language"] != query.language:
                continue
            if query.scope is not None and row["scope"] != query.scope:
                continue
            if row["valid_from"] > query.now:
                continue
            if row["valid_until"] is not None and query.now > row["valid_until"]:
                continue
            eligible[row["chunk_id"]] = KnowledgeChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                section_path=tuple(json.loads(row["section_path_json"])),
                content=row["content"],
                rights_mode=row["rights_mode"],
                language=row["language"],
                scope=row["scope"],
                valid_from=row["valid_from"],
                valid_until=row["valid_until"],
                confidence=row["confidence"],
                version=row["version"],
            )
        return eligible

    def _lexical(self, subqueries: tuple[str, ...], eligible_ids: set[str]) -> list[str]:
        tokens = tuple(
            dict.fromkeys(
                token
                for text in subqueries
                for token in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
                if len(token) > 1
            )
        )
        if not tokens or not eligible_ids:
            return []
        match = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
        rows = self.connection.execute(
            """
            SELECT chunk_id, bm25(knowledge_chunks_fts) AS rank
            FROM knowledge_chunks_fts
            WHERE knowledge_chunks_fts MATCH ?
            ORDER BY rank ASC
            """,
            (match,),
        )
        return [row["chunk_id"] for row in rows if row["chunk_id"] in eligible_ids]

    def _vector(self, text: str, eligible_ids: set[str], k: int) -> list[str]:
        vector = self.embedder.embed(
            f"{self.descriptor.query_instruction}{text}"
            if self.descriptor.query_instruction
            else text
        )
        if len(vector) != self.descriptor.dimensions:
            raise EmbeddingCompatibilityError("query vector dimensions do not match index")
        rows = self.connection.execute(
            f"""
            SELECT chunk_id, distance FROM {self._vector_table}
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
            """,
            (sqlite_vec.serialize_float32(vector), max(1, k)),
        )
        return [row["chunk_id"] for row in rows if row["chunk_id"] in eligible_ids]

    def _graph(
        self,
        seed_chunk_ids: tuple[str, ...],
        eligible: dict[str, KnowledgeChunk],
        allowed_relations: tuple[str, ...],
        depth: int,
    ) -> list[str]:
        if depth == 0 or not seed_chunk_ids:
            return []
        seed_documents = {eligible[item].document_id for item in seed_chunk_ids if item in eligible}
        visited = set(seed_documents)
        frontier = set(seed_documents)
        allowed = set(allowed_relations)
        for _ in range(depth):
            next_frontier: set[str] = set()
            for row in self.connection.execute(
                "SELECT source_id, target_id, relation FROM knowledge_edges_v3"
            ):
                if row["relation"] not in allowed:
                    continue
                if row["source_id"] in frontier and row["target_id"] not in visited:
                    next_frontier.add(row["target_id"])
                if row["target_id"] in frontier and row["source_id"] not in visited:
                    next_frontier.add(row["source_id"])
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        neighbors = visited - seed_documents
        return sorted(
            chunk.chunk_id
            for chunk in eligible.values()
            if chunk.document_id in neighbors
        )

    @staticmethod
    def _semantic_deduplicate(
        ranked_ids: Sequence[str], eligible: dict[str, KnowledgeChunk]
    ) -> list[str]:
        selected: list[str] = []
        normalized: list[str] = []
        for chunk_id in ranked_ids:
            content = " ".join(eligible[chunk_id].content.casefold().split())
            if any(SequenceMatcher(None, content, prior).ratio() >= 0.92 for prior in normalized):
                continue
            selected.append(chunk_id)
            normalized.append(content)
        return selected

    @staticmethod
    def _diversify(
        ranked_ids: Sequence[str],
        eligible: dict[str, KnowledgeChunk],
        limit: int,
        max_per_document: int,
    ) -> list[str]:
        selected: list[str] = []
        counts: dict[str, int] = {}
        for chunk_id in ranked_ids:
            document_id = eligible[chunk_id].document_id
            if counts.get(document_id, 0) >= max_per_document:
                continue
            selected.append(chunk_id)
            counts[document_id] = counts.get(document_id, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _safe_vector_table(version_hash: str) -> str:
        safe = "".join(character for character in version_hash if character.isalnum())[:24]
        if len(safe) < 8:
            raise EmbeddingCompatibilityError("embedding version hash cannot name an index")
        return f"knowledge_vectors_{safe}"

    def close(self) -> None:
        self.connection.close()


class RAGV3Evaluator:
    def evaluate(
        self,
        index: RAGV3Index,
        cases: Sequence[RetrievalEvaluationCaseV2],
        *,
        now: int,
        k: int = 8,
    ) -> RetrievalEvaluationV2:
        if not cases:
            return RetrievalEvaluationV2(0.0, 0.0, 0.0, 0.0, 0.0, 0)
        recalls: list[float] = []
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        citation_precisions: list[float] = []
        redundancies: list[float] = []
        for case in cases:
            packet = index.retrieve(
                RetrievalQueryV3(
                    text=case.query,
                    now=now,
                    language="es",
                    scope="narrative",
                    allowed_rights=("owned_original", "promoted_learning"),
                    limit=k,
                    max_per_document=2,
                )
            )
            ranking = [item.document_id for item in packet.results[:k]]
            relevant = set(case.relevant_document_ids)
            found = relevant & set(ranking)
            recalls.append(len(found) / max(1, len(relevant)))
            first = next(
                (
                    position
                    for position, document_id in enumerate(ranking, 1)
                    if document_id in relevant
                ),
                None,
            )
            reciprocal_ranks.append(1.0 / first if first else 0.0)
            dcg = sum(
                1.0 / math.log2(position + 1)
                for position, document_id in enumerate(ranking, 1)
                if document_id in relevant
            )
            ideal = sum(
                1.0 / math.log2(position + 1)
                for position in range(1, min(k, len(relevant)) + 1)
            )
            ndcgs.append(dcg / ideal if ideal else 0.0)
            citation_precisions.append(
                len(found) / max(1, len(ranking))
            )
            contents = [" ".join(item.content.casefold().split()) for item in packet.results[:k]]
            redundancies.append(
                1 - len(set(contents)) / len(contents) if contents else 0.0
            )
        count = len(cases)
        return RetrievalEvaluationV2(
            recall_at_k=sum(recalls) / count,
            mrr=sum(reciprocal_ranks) / count,
            ndcg_at_k=sum(ndcgs) / count,
            citation_precision=sum(citation_precisions) / count,
            redundancy_rate=sum(redundancies) / count,
            cases=count,
        )

