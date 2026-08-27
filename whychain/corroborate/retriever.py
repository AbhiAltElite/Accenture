"""Retrieval backends for corroboration.

Two implementations behind one protocol. NumpyRetriever is the default and what
the demo runs on; PgVectorRetriever exists for deployment scale. See
DECISIONS.md D-002 for where the threshold between them sits.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

import numpy as np

from whychain.corroborate.documents import Document, Match, sentence_spans
from whychain.corroborate.embedder import Embedder, TfidfSvdEmbedder


@runtime_checkable
class Retriever(Protocol):
    """Windowed semantic search over internal documents."""

    def index(self, documents: list[Document]) -> None: ...

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        window: tuple[datetime, datetime] | None = None,
        min_score: float = 0.0,
    ) -> list[Match]: ...


def _best_span(text: str, query_vec: np.ndarray, embedder: Embedder) -> tuple[tuple[int, int], str]:
    """Pick the sentence within a document that best matches the query.

    Citing a document is a reference; citing the sentence is evidence.
    """
    spans = sentence_spans(text)
    if len(spans) == 1:
        s, e = spans[0]
        return spans[0], text[s:e]
    sentences = [text[s:e] for s, e in spans]
    scores = embedder.encode(sentences) @ query_vec
    best = int(np.argmax(scores))
    return spans[best], sentences[best]


class NumpyRetriever:
    """Brute-force cosine similarity over an in-memory matrix.

    At demo corpus size this is exact and faster end-to-end than an approximate
    index, because there is no round trip and no recall trade-off. It becomes
    the wrong choice somewhere around a million vectors.
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.embedder = embedder or TfidfSvdEmbedder()
        self._docs: list[Document] = []
        self._matrix: np.ndarray | None = None

    def index(self, documents: list[Document]) -> None:
        if not documents:
            raise ValueError("cannot index an empty document set")
        self._docs = list(documents)
        texts = [d.text for d in self._docs]
        self.embedder.fit(texts)
        self._matrix = self.embedder.encode(texts)

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        window: tuple[datetime, datetime] | None = None,
        min_score: float = 0.0,
    ) -> list[Match]:
        if self._matrix is None:
            raise RuntimeError("retriever must be indexed before searching")

        # Window first: corroboration is only meaningful inside the anomaly period.
        candidates = range(len(self._docs))
        if window is not None:
            start, end = window
            candidates = [i for i in candidates if start <= self._docs[i].ts <= end]
            if not candidates:
                return []

        query_vec = self.embedder.encode([query])[0]
        idx = np.fromiter(candidates, dtype=np.int64)
        scores = self._matrix[idx] @ query_vec

        order = np.argsort(-scores)[:k]
        matches: list[Match] = []
        for pos in order:
            score = float(scores[pos])
            if score < min_score:
                continue
            doc = self._docs[int(idx[pos])]
            span, quote = _best_span(doc.text, query_vec, self.embedder)
            matches.append(
                Match(
                    doc_id=doc.doc_id,
                    source_id=doc.source_id,
                    score=score,
                    ts=doc.ts,
                    span=span,
                    quote=quote,
                )
            )
        return matches


class PgVectorRetriever:
    """Postgres + pgvector backend for deployment scale.

    Same protocol as NumpyRetriever, so the pipeline is unaffected by the swap.
    Requires the pgvector extension:

        brew install pgvector
        psql -d whychain -c 'CREATE EXTENSION IF NOT EXISTS vector;'
    """

    def __init__(self, dsn: str, embedder: Embedder | None = None, table: str = "documents") -> None:
        self.dsn = dsn
        self.table = table
        self.embedder = embedder or TfidfSvdEmbedder()
        self._conn = None

    def _connect(self):
        if self._conn is None:
            try:
                import psycopg  # imported lazily so the default path needs no driver
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "PgVectorRetriever needs psycopg: pip install 'psycopg[binary]'"
                ) from exc
            self._conn = psycopg.connect(self.dsn)
        return self._conn

    def index(self, documents: list[Document]) -> None:
        if not documents:
            raise ValueError("cannot index an empty document set")
        texts = [d.text for d in documents]
        self.embedder.fit(texts)
        vectors = self.embedder.encode(texts)

        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {self.table}")
            cur.execute(
                f"CREATE TABLE {self.table} ("
                "  doc_id text PRIMARY KEY,"
                "  source_id text NOT NULL,"
                "  text text NOT NULL,"
                "  ts timestamptz NOT NULL,"
                f" embedding vector({self.embedder.dim}))"
            )
            cur.executemany(
                f"INSERT INTO {self.table} (doc_id, source_id, text, ts, embedding) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    (d.doc_id, d.source_id, d.text, d.ts, vec.tolist())
                    for d, vec in zip(documents, vectors, strict=True)
                ],
            )
        conn.commit()

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        window: tuple[datetime, datetime] | None = None,
        min_score: float = 0.0,
    ) -> list[Match]:
        query_vec = self.embedder.encode([query])[0]

        # Parameterised throughout; the table name is developer-controlled, never user input.
        sql = f"SELECT doc_id, source_id, text, ts, 1 - (embedding <=> %s::vector) AS score FROM {self.table}"
        params: list[object] = [query_vec.tolist()]
        if window is not None:
            sql += " WHERE ts BETWEEN %s AND %s"
            params.extend(window)
        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([query_vec.tolist(), k])

        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        matches: list[Match] = []
        for doc_id, source_id, text, ts, score in rows:
            if score < min_score:
                continue
            span, quote = _best_span(text, query_vec, self.embedder)
            matches.append(
                Match(
                    doc_id=doc_id, source_id=source_id, score=float(score),
                    ts=ts, span=span, quote=quote,
                )
            )
        return matches


def build_retriever(backend: str = "numpy", **kwargs) -> Retriever:
    """Select a retrieval backend. Default is numpy; see DECISIONS.md D-002."""
    match backend:
        case "numpy":
            return NumpyRetriever(**kwargs)
        case "pgvector":
            return PgVectorRetriever(**kwargs)
        case _:
            raise ValueError(f"unknown retrieval backend: {backend!r}")
