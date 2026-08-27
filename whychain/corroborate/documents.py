"""Document and match types for the corroboration stage."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class Document(BaseModel):
    """One retrievable internal document: a ticket, a rep note, a release log entry."""

    doc_id: str
    source_id: str
    text: str
    ts: datetime
    metadata: dict[str, str] = Field(default_factory=dict)


class Match(BaseModel):
    """A retrieval hit, carrying the span needed for a citation.

    span and quote are what make this evidence rather than a reference: the
    reader is shown the exact words, not told which document to go and read.
    """

    doc_id: str
    source_id: str
    score: float
    ts: datetime
    span: tuple[int, int]
    quote: str


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of each sentence, used to cite a passage rather than a file."""
    spans: list[tuple[int, int]] = []
    start = 0
    for part in _SENTENCE_END.split(text):
        if not part:
            continue
        idx = text.find(part, start)
        if idx == -1:
            continue
        spans.append((idx, idx + len(part)))
        start = idx + len(part)
    return spans or [(0, len(text))]
