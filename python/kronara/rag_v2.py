from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from kronara.intelligence import reciprocal_rank_fusion


class Embedder(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    def score(self, query: str, chunk: "KnowledgeChunk") -> float: ...


class DeterministicHashEmbedder:
    """Small local embedding fallback for evaluation and offline recovery."""

    def __init__(self, dimensions: int = 64):
        if dimensions < 8:
            raise ValueError("dimensions must be at least eight")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        return vector


class ControlledQueryExpander:
    DEFAULT_LEXICON = {
        "retención": ("finalización", "abandono", "permanencia"),
        "derechos": ("licencia", "permiso", "atribución"),
        "gancho": ("hook", "apertura", "primeros segundos"),
        "contradicción": ("evidencia contraria", "conflicto", "disputa"),
        "voz": ("narrador", "locución", "voice"),
    }

    def __init__(
        self,
        lexicon: dict[str, tuple[str, ...]] | None = None,
        *,
        max_terms: int = 6,
    ):
        if max_terms < 0 or max_terms > 20:
            raise ValueError("max_terms must be between zero and twenty")
        self.lexicon = lexicon or self.DEFAULT_LEXICON
        self.max_terms = max_terms

    def expand(self, query: str) -> tuple[str, ...]:
        if self.max_terms == 0:
            return ()
        tokens = set(re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE))
        expanded: list[str] = []
        seen: set[str] = set()
        for key, alternatives in self.lexicon.items():
            if key.casefold() not in tokens:
                continue
            for term in alternatives:
                normalized = " ".join(term.split())
                fingerprint = normalized.casefold()
                if normalized and fingerprint not in seen:
                    expanded.append(normalized)
                    seen.add(fingerprint)
                if len(expanded) >= self.max_terms:
                    return tuple(expanded)
        return tuple(expanded)


@dataclass(frozen=True)
class IngestDocument:
    document_id: str
    title: str
    content: str
    rights_mode: str
    language: str
    scope: str
    valid_from: int
    valid_until: int | None
    confidence: float = 1.0
    version: int = 1


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    section_path: tuple[str, ...]
    content: str
    rights_mode: str
    language: str
    scope: str
    valid_from: int
    valid_until: int | None
    confidence: float
    version: int


@dataclass(frozen=True)
class RetrievalQueryV2:
    text: str
    now: int
    language: str | None = None
    scope: str | None = None
    allowed_rights: tuple[str, ...] = (
        "owned_original",
        "licensed_adaptation",
        "promoted_learning",
    )
    expanded_terms: tuple[str, ...] = ()
    auto_expand: bool = True
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


@dataclass(frozen=True)
class RetrievalResultV2:
    chunk_id: str
    document_id: str
    section_path: tuple[str, ...]
    content: str
    score: float
    confidence: float
    citation_uri: str


@dataclass(frozen=True)
class RetrievalPacketV2:
    results: tuple[RetrievalResultV2, ...]
    filtered_document_ids: tuple[str, ...]
    candidate_count: int


@dataclass(frozen=True)
class RAGEvaluationCase:
    query: str
    relevant_document_ids: tuple[str, ...]


@dataclass(frozen=True)
class RAGEvaluation:
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_precision: float
    redundancy_rate: float
    cases: int


@dataclass(frozen=True)
class RAGPromotionDecision:
    promoted: bool
    reason: str
    ndcg_lift: float
    citation_delta: float
    redundancy_delta: float


class RAGPromotionGate:
    """Promotes retrieval changes only when quality improves without regressions."""

    def __init__(
        self,
        *,
        minimum_ndcg_lift: float = 0.02,
        minimum_citation_precision: float = 0.75,
        maximum_redundancy: float = 0.15,
    ):
        if minimum_ndcg_lift < 0:
            raise ValueError("minimum_ndcg_lift cannot be negative")
        if not 0 <= minimum_citation_precision <= 1:
            raise ValueError("minimum_citation_precision must be between zero and one")
        if not 0 <= maximum_redundancy <= 1:
            raise ValueError("maximum_redundancy must be between zero and one")
        self.minimum_ndcg_lift = minimum_ndcg_lift
        self.minimum_citation_precision = minimum_citation_precision
        self.maximum_redundancy = maximum_redundancy

    def evaluate(
        self, baseline: RAGEvaluation, candidate: RAGEvaluation
    ) -> RAGPromotionDecision:
        metrics = (
            baseline.recall_at_k,
            baseline.mrr,
            baseline.ndcg_at_k,
            baseline.citation_precision,
            baseline.redundancy_rate,
            candidate.recall_at_k,
            candidate.mrr,
            candidate.ndcg_at_k,
            candidate.citation_precision,
            candidate.redundancy_rate,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in metrics):
            return RAGPromotionDecision(False, "invalid_metric", 0.0, 0.0, 0.0)
        ndcg_lift = candidate.ndcg_at_k - baseline.ndcg_at_k
        citation_delta = candidate.citation_precision - baseline.citation_precision
        redundancy_delta = candidate.redundancy_rate - baseline.redundancy_rate
        reason = "material_quality_gain"
        promoted = True
        if baseline.cases <= 0 or candidate.cases != baseline.cases:
            reason, promoted = "incomparable_evaluation_set", False
        elif ndcg_lift < self.minimum_ndcg_lift:
            reason, promoted = "ndcg_lift_below_threshold", False
        elif candidate.recall_at_k < baseline.recall_at_k:
            reason, promoted = "recall_regression", False
        elif candidate.citation_precision < self.minimum_citation_precision:
            reason, promoted = "citation_precision_below_threshold", False
        elif candidate.redundancy_rate > self.maximum_redundancy:
            reason, promoted = "redundancy_above_threshold", False
        return RAGPromotionDecision(
            promoted=promoted,
            reason=reason,
            ndcg_lift=ndcg_lift,
            citation_delta=citation_delta,
            redundancy_delta=redundancy_delta,
        )


@dataclass(frozen=True)
class KnowledgeEdge:
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0


class HierarchicalChunker:
    def __init__(self, max_characters: int = 900):
        if max_characters < 40:
            raise ValueError("max characters must be at least 40")
        self.max_characters = max_characters

    def chunk(self, document: IngestDocument) -> tuple[KnowledgeChunk, ...]:
        chunks: list[KnowledgeChunk] = []
        for section_path, body in self._sections(document):
            for position, content in enumerate(self._split_body(body)):
                normalized = " ".join(content.split())
                digest = hashlib.sha256(
                    f"{document.document_id}|{'/'.join(section_path)}|{position}|{normalized}".encode(
                        "utf-8"
                    )
                ).hexdigest()[:20]
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=f"{document.document_id}:{digest}",
                        document_id=document.document_id,
                        section_path=section_path,
                        content=normalized,
                        rights_mode=document.rights_mode,
                        language=document.language,
                        scope=document.scope,
                        valid_from=document.valid_from,
                        valid_until=document.valid_until,
                        confidence=document.confidence,
                        version=document.version,
                    )
                )
        return tuple(chunks)

    def _sections(
        self, document: IngestDocument
    ) -> tuple[tuple[tuple[str, ...], str], ...]:
        sections: list[tuple[tuple[str, ...], str]] = []
        headings: list[str] = []
        body: list[str] = []

        def flush() -> None:
            content = "\n".join(body).strip()
            if content:
                sections.append((tuple(headings or [document.title]), content))

        for line in document.content.replace("\r\n", "\n").split("\n"):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                flush()
                body = []
                level = len(match.group(1))
                headings = headings[: level - 1]
                headings.append(match.group(2))
            else:
                body.append(line)
        flush()
        return tuple(sections)

    def _split_body(self, body: str) -> tuple[str, ...]:
        paragraphs = [
            " ".join(item.split())
            for item in re.split(r"\n\s*\n", body)
            if item.strip()
        ]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            for piece in self._hard_split(paragraph):
                candidate = f"{current}\n\n{piece}".strip() if current else piece
                if len(candidate) <= self.max_characters:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = piece
        if current:
            chunks.append(current)
        return tuple(chunks)

    def _hard_split(self, text: str) -> tuple[str, ...]:
        if len(text) <= self.max_characters:
            return (text,)
        pieces: list[str] = []
        current: list[str] = []
        for word in text.split():
            candidate = " ".join((*current, word))
            if current and len(candidate) > self.max_characters:
                pieces.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            pieces.append(" ".join(current))
        return tuple(pieces)


class RAGV2Index:
    def __init__(
        self,
        embedder: Embedder,
        *,
        reranker: Reranker | None = None,
        chunker: HierarchicalChunker | None = None,
        expander: ControlledQueryExpander | None = None,
        database: Path | None = None,
    ):
        self.embedder = embedder
        self.reranker = reranker
        self.chunker = chunker or HierarchicalChunker()
        self.expander = expander or ControlledQueryExpander()
        self.database = Path(database) if database is not None else None
        self.connection: sqlite3.Connection | None = None
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._vectors: dict[str, list[float]] = {}
        self._documents: dict[str, IngestDocument] = {}
        self._tombstones: set[str] = set()
        self._edges: set[KnowledgeEdge] = set()

    def initialize(self) -> None:
        if self.database is None or self.connection is not None:
            return
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database)
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS rag_v2_documents (
                document_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rag_v2_tombstones (
                document_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS rag_v2_edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                weight REAL NOT NULL,
                PRIMARY KEY(source_id, target_id, relation)
            );
            """
        )
        self.connection.commit()
        for (payload_json,) in self.connection.execute(
            "SELECT payload_json FROM rag_v2_documents ORDER BY document_id"
        ):
            self._upsert_memory(IngestDocument(**json.loads(payload_json)))
        self._tombstones = {
            str(row[0])
            for row in self.connection.execute("SELECT document_id FROM rag_v2_tombstones")
        }
        self._edges = {
            KnowledgeEdge(str(source), str(target), str(relation), float(weight))
            for source, target, relation, weight in self.connection.execute(
                "SELECT source_id, target_id, relation, weight FROM rag_v2_edges"
            )
        }

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def upsert(self, document: IngestDocument) -> None:
        self._upsert_memory(document)
        if self.connection is not None:
            self.connection.execute(
                """
                INSERT INTO rag_v2_documents(document_id, payload_json) VALUES (?, ?)
                ON CONFLICT(document_id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (
                    document.document_id,
                    json.dumps(document.__dict__, sort_keys=True, separators=(",", ":")),
                ),
            )
            self.connection.execute(
                "DELETE FROM rag_v2_tombstones WHERE document_id = ?", (document.document_id,)
            )
            self.connection.commit()

    def _upsert_memory(self, document: IngestDocument) -> None:
        self._documents[document.document_id] = document
        self._tombstones.discard(document.document_id)
        old_ids = [
            key
            for key, chunk in self._chunks.items()
            if chunk.document_id == document.document_id
        ]
        for chunk_id in old_ids:
            self._chunks.pop(chunk_id, None)
            self._vectors.pop(chunk_id, None)
        seen: set[str] = set()
        for chunk in self.chunker.chunk(document):
            normalized = " ".join(chunk.content.casefold().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            self._chunks[chunk.chunk_id] = chunk
            self._vectors[chunk.chunk_id] = self.embedder.embed(chunk.content)

    def tombstone(self, document_id: str) -> None:
        self._tombstones.add(document_id)
        if self.connection is not None:
            self.connection.execute(
                "INSERT OR IGNORE INTO rag_v2_tombstones(document_id) VALUES (?)",
                (document_id,),
            )
            self.connection.commit()

    def link_documents(
        self,
        source_id: str,
        target_id: str,
        relation: str = "related",
        weight: float = 1.0,
    ) -> None:
        if not source_id.strip() or not target_id.strip() or not relation.strip():
            raise ValueError("graph edge identity is required")
        if not 0 < weight <= 1:
            raise ValueError("graph edge weight must be between zero and one")
        edge = KnowledgeEdge(source_id, target_id, relation, weight)
        self._edges.add(edge)
        if self.connection is not None:
            self.connection.execute(
                "INSERT OR REPLACE INTO rag_v2_edges VALUES (?, ?, ?, ?)",
                (source_id, target_id, relation, weight),
            )
            self.connection.commit()

    def graph_neighbors(
        self,
        seed_ids: tuple[str, ...],
        allowed_relations: tuple[str, ...],
        max_depth: int,
    ) -> tuple[str, ...]:
        if max_depth < 0 or max_depth > 3:
            raise ValueError("graph depth must be between zero and three")
        allowed = set(allowed_relations)
        visited = set(seed_ids)
        frontier = set(seed_ids)
        discovered: set[str] = set()
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for edge in self._edges:
                if edge.relation not in allowed:
                    continue
                neighbor = None
                if edge.source_id in frontier:
                    neighbor = edge.target_id
                elif edge.target_id in frontier:
                    neighbor = edge.source_id
                if neighbor is not None and neighbor not in visited:
                    discovered.add(neighbor)
                    next_frontier.add(neighbor)
            visited.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        return tuple(sorted(discovered))

    def retrieve(self, query: RetrievalQueryV2) -> RetrievalPacketV2:
        if not query.text.strip() or query.limit < 1:
            return RetrievalPacketV2((), (), 0)
        if query.graph_depth < 0 or query.graph_depth > 3:
            raise ValueError("graph depth must be between zero and three")
        eligible: list[KnowledgeChunk] = []
        filtered: set[str] = set()
        for document_id, document in self._documents.items():
            if not self._eligible(document, query):
                filtered.add(document_id)
        for chunk in self._chunks.values():
            if chunk.document_id not in filtered:
                eligible.append(chunk)

        deduplicated: dict[str, KnowledgeChunk] = {}
        for chunk in sorted(eligible, key=lambda item: (-item.confidence, item.chunk_id)):
            fingerprint = " ".join(chunk.content.casefold().split())
            deduplicated.setdefault(fingerprint, chunk)
        eligible = list(deduplicated.values())

        automatic_terms = self.expander.expand(query.text) if query.auto_expand else ()
        expanded_terms = tuple(dict.fromkeys((*query.expanded_terms, *automatic_terms)))
        query_text = " ".join((query.text, *expanded_terms))
        query_tokens = set(self._tokens(query_text))
        query_vector = self.embedder.embed(query_text)
        lexical_scores = {
            chunk.chunk_id: self._lexical_score(query_tokens, chunk.content)
            for chunk in eligible
        }
        lexical = sorted(
            (chunk for chunk in eligible if lexical_scores[chunk.chunk_id] > 0),
            key=lambda chunk: (
                -lexical_scores[chunk.chunk_id],
                chunk.chunk_id,
            ),
        )
        semantic_scores = {
            chunk.chunk_id: self._cosine(
                query_vector, self._vectors[chunk.chunk_id]
            )
            for chunk in eligible
        }
        semantic = sorted(
            (chunk for chunk in eligible if semantic_scores[chunk.chunk_id] > 0),
            key=lambda chunk: (
                -semantic_scores[chunk.chunk_id],
                chunk.chunk_id,
            ),
        )
        graph = self._graph_ranking(
            lexical[:3],
            eligible,
            allowed_relations=query.allowed_relations,
            max_depth=query.graph_depth,
        )
        fused = reciprocal_rank_fusion(
            [
                [chunk.chunk_id for chunk in lexical],
                [chunk.chunk_id for chunk in semantic],
                [chunk.chunk_id for chunk in graph],
            ]
        )
        fused_scores = {item.item_id: item.score for item in fused}
        ranked = sorted(
            eligible,
            key=lambda chunk: (
                -(
                    self.reranker.score(query.text, chunk)
                    if self.reranker
                    else fused_scores.get(chunk.chunk_id, 0.0)
                ),
                -fused_scores.get(chunk.chunk_id, 0.0),
                chunk.chunk_id,
            ),
        )
        selected: list[KnowledgeChunk] = []
        per_document: dict[str, int] = {}
        for chunk in ranked:
            count = per_document.get(chunk.document_id, 0)
            if count >= max(1, query.max_per_document):
                continue
            selected.append(chunk)
            per_document[chunk.document_id] = count + 1
            if len(selected) >= query.limit:
                break
        results = tuple(
            RetrievalResultV2(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                section_path=chunk.section_path,
                content=chunk.content,
                score=fused_scores.get(chunk.chunk_id, 0.0) * chunk.confidence,
                confidence=chunk.confidence,
                citation_uri=f"kronara://knowledge/{chunk.document_id}/{chunk.chunk_id}",
            )
            for chunk in selected
        )
        return RetrievalPacketV2(results, tuple(sorted(filtered)), len(eligible))

    def _eligible(self, document: IngestDocument, query: RetrievalQueryV2) -> bool:
        return (
            document.document_id not in self._tombstones
            and document.rights_mode in query.allowed_rights
            and (query.language is None or document.language == query.language)
            and (query.scope is None or document.scope == query.scope)
            and document.valid_from <= query.now
            and (document.valid_until is None or query.now <= document.valid_until)
        )

    def _graph_ranking(
        self,
        seeds: Sequence[KnowledgeChunk],
        eligible: Sequence[KnowledgeChunk],
        *,
        allowed_relations: tuple[str, ...],
        max_depth: int,
    ) -> list[KnowledgeChunk]:
        seed_documents = tuple(sorted({chunk.document_id for chunk in seeds}))
        neighbors = set(
            self.graph_neighbors(seed_documents, allowed_relations, max_depth)
        )
        return [chunk for chunk in eligible if chunk.document_id in neighbors]

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        return tuple(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))

    def _lexical_score(self, query_tokens: set[str], content: str) -> float:
        content_tokens = set(self._tokens(content))
        return len(query_tokens & content_tokens) / max(1, len(query_tokens))

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)


class RAGEvaluator:
    def evaluate(
        self,
        index: RAGV2Index,
        cases: Sequence[RAGEvaluationCase],
        *,
        now: int,
        k: int = 8,
    ) -> RAGEvaluation:
        if not cases:
            return RAGEvaluation(0.0, 0.0, 0.0, 0.0, 0.0, 0)
        recalls: list[float] = []
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        citation_precisions: list[float] = []
        redundancies: list[float] = []
        for case in cases:
            packet = index.retrieve(RetrievalQueryV2(case.query, now=now, limit=k))
            ranking = [result.document_id for result in packet.results]
            relevant = set(case.relevant_document_ids)
            found = relevant & set(ranking[:k])
            recalls.append(len(found) / max(1, len(relevant)))
            first = next(
                (
                    position
                    for position, item in enumerate(ranking[:k], 1)
                    if item in relevant
                ),
                None,
            )
            reciprocal_ranks.append(1.0 / first if first else 0.0)
            dcg = sum(
                1.0 / math.log2(position + 1)
                for position, item in enumerate(ranking[:k], 1)
                if item in relevant
            )
            ideal_count = min(len(relevant), k)
            ideal = sum(
                1.0 / math.log2(position + 1)
                for position in range(1, ideal_count + 1)
            )
            ndcgs.append(dcg / ideal if ideal else 0.0)
            citation_precisions.append(
                sum(1 for item in ranking[:k] if item in relevant)
                / max(1, len(ranking[:k]))
            )
            contents = [
                " ".join(result.content.casefold().split())
                for result in packet.results[:k]
            ]
            redundancies.append(
                1 - len(set(contents)) / len(contents) if contents else 0.0
            )
        count = len(cases)
        return RAGEvaluation(
            recall_at_k=sum(recalls) / count,
            mrr=sum(reciprocal_ranks) / count,
            ndcg_at_k=sum(ndcgs) / count,
            citation_precision=sum(citation_precisions) / count,
            redundancy_rate=sum(redundancies) / count,
            cases=count,
        )
