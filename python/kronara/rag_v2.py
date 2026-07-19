from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from kronara.intelligence import reciprocal_rank_fusion


class Embedder(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    def score(self, query: str, chunk: "KnowledgeChunk") -> float: ...


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
    cases: int


class HierarchicalChunker:
    def __init__(self, max_characters: int = 900):
        if max_characters < 40:
            raise ValueError("max characters must be at least 40")
        self.max_characters = max_characters

    def chunk(self, document: IngestDocument) -> tuple[KnowledgeChunk, ...]:
        sections = self._sections(document)
        chunks: list[KnowledgeChunk] = []
        for section_path, body in sections:
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
        paragraphs = [" ".join(item.split()) for item in re.split(r"\n\s*\n", body) if item.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            pieces = self._hard_split(paragraph)
            for piece in pieces:
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
        words = text.split()
        pieces: list[str] = []
        current: list[str] = []
        for word in words:
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
    ):
        self.embedder = embedder
        self.reranker = reranker
        self.chunker = chunker or HierarchicalChunker()
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._vectors: dict[str, list[float]] = {}
        self._documents: dict[str, IngestDocument] = {}
        self._tombstones: set[str] = set()
        self._edges: set[tuple[str, str]] = set()

    def upsert(self, document: IngestDocument) -> None:
        self._documents[document.document_id] = document
        self._tombstones.discard(document.document_id)
        old_ids = [key for key, chunk in self._chunks.items() if chunk.document_id == document.document_id]
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

    def link_documents(self, source_id: str, target_id: str) -> None:
        self._edges.add((source_id, target_id))

    def retrieve(self, query: RetrievalQueryV2) -> RetrievalPacketV2:
        if not query.text.strip() or query.limit < 1:
            return RetrievalPacketV2((), (), 0)
        eligible: list[KnowledgeChunk] = []
        filtered: set[str] = set()
        for document_id, document in self._documents.items():
            if not self._eligible(document, query):
                filtered.add(document_id)
        for chunk in self._chunks.values():
            if chunk.document_id not in filtered:
                eligible.append(chunk)

        query_text = " ".join((query.text, *query.expanded_terms))
        query_tokens = set(self._tokens(query_text))
        query_vector = self.embedder.embed(query_text)
        lexical = sorted(
            eligible,
            key=lambda chunk: (-self._lexical_score(query_tokens, chunk.content), chunk.chunk_id),
        )
        semantic = sorted(
            eligible,
            key=lambda chunk: (-self._cosine(query_vector, self._vectors[chunk.chunk_id]), chunk.chunk_id),
        )
        graph = self._graph_ranking(lexical[:3], eligible)
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
                chunk.chunk_id,
                chunk.document_id,
                chunk.section_path,
                chunk.content,
                fused_scores.get(chunk.chunk_id, 0.0) * chunk.confidence,
                chunk.confidence,
                f"kronara://knowledge/{chunk.document_id}/{chunk.chunk_id}",
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
        self, seeds: Sequence[KnowledgeChunk], eligible: Sequence[KnowledgeChunk]
    ) -> list[KnowledgeChunk]:
        seed_documents = {chunk.document_id for chunk in seeds}
        neighbors = {
            target if source in seed_documents else source
            for source, target in self._edges
            if source in seed_documents or target in seed_documents
        }
        return [chunk for chunk in eligible if chunk.document_id in neighbors]

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        return tuple(re.findall(r"[\wáéíóúñü]+", text.casefold(), flags=re.UNICODE))

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
            return RAGEvaluation(0.0, 0.0, 0.0, 0)
        recalls: list[float] = []
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        for case in cases:
            packet = index.retrieve(RetrievalQueryV2(case.query, now=now, limit=k))
            ranking = [result.document_id for result in packet.results]
            relevant = set(case.relevant_document_ids)
            found = relevant & set(ranking[:k])
            recalls.append(len(found) / max(1, len(relevant)))
            first = next(
                (position for position, item in enumerate(ranking[:k], 1) if item in relevant),
                None,
            )
            reciprocal_ranks.append(1.0 / first if first else 0.0)
            dcg = sum(
                1.0 / math.log2(position + 1)
                for position, item in enumerate(ranking[:k], 1)
                if item in relevant
            )
            ideal_count = min(len(relevant), k)
            ideal = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_count + 1))
            ndcgs.append(dcg / ideal if ideal else 0.0)
        count = len(cases)
        return RAGEvaluation(
            sum(recalls) / count,
            sum(reciprocal_ranks) / count,
            sum(ndcgs) / count,
            count,
        )
