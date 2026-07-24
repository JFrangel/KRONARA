from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import sqlite_vec
from sqlite_vec import serialize_float32

from kronara.intelligence import reciprocal_rank_fusion


class Embedder(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    content: str
    rights_mode: str
    confidence: float


@dataclass(frozen=True)
class KnowledgeResult:
    document_id: str
    title: str
    score: float
    citation_uri: str


class LocalHybridIndex:
    def __init__(self, database: Path, embedder: Embedder):
        self.database = Path(database)
        self.embedder = embedder
        self.connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database, check_same_thread=False)
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        connection.executescript(
            f"""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                document_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                rights_mode TEXT NOT NULL,
                confidence REAL NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                document_id UNINDEXED, title, content
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_vectors USING vec0(
                document_id TEXT PRIMARY KEY,
                embedding float[{int(self.embedder.dimensions)}]
            );
            CREATE TABLE IF NOT EXISTS knowledge_edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                PRIMARY KEY(source_id, target_id, relation)
            );
            """
        )
        connection.commit()
        self.connection = connection

    def _db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("knowledge index is not initialized")
        return self.connection

    def upsert(self, document: KnowledgeDocument) -> None:
        db = self._db()
        db.execute(
            """INSERT INTO knowledge_documents VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET title=excluded.title,
            content=excluded.content, rights_mode=excluded.rights_mode,
            confidence=excluded.confidence""",
            (
                document.document_id,
                document.title,
                document.content,
                document.rights_mode,
                document.confidence,
            ),
        )
        db.execute("DELETE FROM knowledge_fts WHERE document_id = ?", (document.document_id,))
        db.execute("DELETE FROM knowledge_vectors WHERE document_id = ?", (document.document_id,))
        if document.rights_mode != "reference_only":
            db.execute(
                "INSERT INTO knowledge_fts(document_id, title, content) VALUES (?, ?, ?)",
                (document.document_id, document.title, document.content),
            )
            vector = self.embedder.embed(f"{document.title}\n{document.content}")
            db.execute(
                "INSERT INTO knowledge_vectors(document_id, embedding) VALUES (?, ?)",
                (document.document_id, serialize_float32(vector)),
            )
        db.commit()

    def link(self, source_id: str, target_id: str, relation: str) -> None:
        self._db().execute(
            "INSERT OR IGNORE INTO knowledge_edges VALUES (?, ?, ?)",
            (source_id, target_id, relation),
        )
        self._db().commit()

    def search(self, query: str, limit: int = 8) -> list[KnowledgeResult]:
        if not query.strip():
            return []
        db = self._db()
        tokens = re.findall(r"[\wáéíóúñü]+", query.lower(), flags=re.UNICODE)
        lexical_query = " OR ".join(f'"{token}"' for token in tokens)
        lexical = (
            [row[0] for row in db.execute(
                "SELECT document_id FROM knowledge_fts WHERE knowledge_fts MATCH ? ORDER BY bm25(knowledge_fts) LIMIT ?",
                (lexical_query, limit * 3),
            )]
            if lexical_query
            else []
        )
        vector = self.embedder.embed(query)
        semantic = [
            row[0]
            for row in db.execute(
                "SELECT document_id FROM knowledge_vectors WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (serialize_float32(vector), max(1, limit * 3)),
            )
        ]
        seeds = list(dict.fromkeys(lexical[:3] + semantic[:3]))
        graph: list[str] = []
        for seed in seeds:
            graph.extend(
                row[0]
                for row in db.execute(
                    """SELECT CASE WHEN source_id = ? THEN target_id ELSE source_id END
                    FROM knowledge_edges WHERE source_id = ? OR target_id = ?""",
                    (seed, seed, seed),
                )
            )
        fused = reciprocal_rank_fusion([lexical, semantic, graph])
        results: list[KnowledgeResult] = []
        for ranked in fused:
            row = db.execute(
                "SELECT title, rights_mode, confidence FROM knowledge_documents WHERE document_id = ?",
                (ranked.item_id,),
            ).fetchone()
            if row and row[1] != "reference_only":
                results.append(
                    KnowledgeResult(
                        ranked.item_id,
                        row[0],
                        ranked.score * float(row[2]),
                        f"kronara://knowledge/{ranked.item_id}",
                    )
                )
            if len(results) >= limit:
                break
        return results

