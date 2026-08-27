"""Retrieval backends: protocol conformance, windowing, and span citation."""

from datetime import UTC, datetime

import pytest

from whychain.corroborate import (
    Document,
    NumpyRetriever,
    PgVectorRetriever,
    Retriever,
    TfidfSvdEmbedder,
    build_retriever,
    sentence_spans,
)

TICKETS = [
    ("tk_01", "Checkout fails on the mobile app. The payment page will not load.", datetime(2026, 8, 11, tzinfo=UTC)),
    ("tk_02", "Delivery arrived three days late in Pune.", datetime(2026, 8, 12, tzinfo=UTC)),
    ("tk_03", "App crashes at the payment step since the update. Cannot pay at all.", datetime(2026, 8, 12, tzinfo=UTC)),
    ("tk_04", "Product quality was excellent and delivery was prompt.", datetime(2026, 8, 3, tzinfo=UTC)),
    ("tk_05", "Unable to complete purchase on Android. The card entry page is blank.", datetime(2026, 8, 13, tzinfo=UTC)),
    ("tk_06", "Requesting a refund for a damaged item.", datetime(2026, 7, 20, tzinfo=UTC)),
]


@pytest.fixture
def documents() -> list[Document]:
    return [Document(doc_id=i, source_id="voice_ops", text=t, ts=ts) for i, t, ts in TICKETS]


@pytest.fixture
def retriever(documents) -> NumpyRetriever:
    r = NumpyRetriever(TfidfSvdEmbedder(dim=16, random_state=0))
    r.index(documents)
    return r


class TestProtocol:
    def test_both_backends_satisfy_the_protocol(self):
        """The pipeline must not care which backend it was handed."""
        assert isinstance(NumpyRetriever(), Retriever)
        assert isinstance(PgVectorRetriever(dsn="postgresql://localhost/x"), Retriever)

    def test_factory_selects_backend(self):
        assert isinstance(build_retriever("numpy"), NumpyRetriever)
        assert isinstance(build_retriever("pgvector", dsn="postgresql://localhost/x"), PgVectorRetriever)

    def test_factory_rejects_unknown_backend(self):
        with pytest.raises(ValueError, match="unknown retrieval backend"):
            build_retriever("elasticsearch")


class TestSearch:
    def test_finds_semantically_related_tickets(self, retriever):
        hits = retriever.search("mobile checkout payment failure", k=3)
        found = {m.doc_id for m in hits}
        assert "tk_01" in found, "the clearest checkout complaint should rank"
        assert hits[0].score > hits[-1].score, "results must be ordered by score"

    def test_ranks_relevant_above_irrelevant(self, retriever):
        hits = {m.doc_id: m.score for m in retriever.search("checkout payment broken", k=6)}
        assert hits["tk_01"] > hits["tk_06"], "a checkout ticket must outrank a refund request"

    def test_min_score_filters(self, retriever):
        assert retriever.search("checkout payment", k=6, min_score=0.99) == []

    def test_unindexed_retriever_refuses(self):
        with pytest.raises(RuntimeError, match="must be indexed"):
            NumpyRetriever().search("anything")

    def test_empty_corpus_is_an_error(self):
        """Silently indexing nothing would make every later search look conclusive."""
        with pytest.raises(ValueError, match="empty document set"):
            NumpyRetriever().index([])


class TestWindowing:
    """Corroboration is only meaningful inside the anomaly window."""

    def test_window_excludes_documents_outside_it(self, retriever):
        window = (datetime(2026, 8, 11, tzinfo=UTC), datetime(2026, 8, 13, 23, 59, tzinfo=UTC))
        hits = retriever.search("delivery problem", k=6, window=window)
        assert all(window[0] <= m.ts <= window[1] for m in hits)
        assert "tk_06" not in {m.doc_id for m in hits}, "July ticket is outside an August window"

    def test_empty_window_returns_nothing(self, retriever):
        hits = retriever.search("checkout", window=(datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 2, tzinfo=UTC)))
        assert hits == []


class TestSpanCitation:
    """A citation must point at the sentence, not just the document."""

    def test_span_indexes_the_quoted_text(self, retriever, documents):
        by_id = {d.doc_id: d for d in documents}
        for match in retriever.search("payment page will not load", k=3):
            start, end = match.span
            assert by_id[match.doc_id].text[start:end] == match.quote

    def test_quote_is_the_relevant_sentence(self, retriever):
        hits = retriever.search("mobile checkout fails", k=1)
        assert "checkout" in hits[0].quote.lower()


class TestSentenceSpans:
    def test_splits_on_terminators(self):
        text = "Checkout broke. Payment failed twice."
        spans = sentence_spans(text)
        assert [text[s:e] for s, e in spans] == ["Checkout broke.", "Payment failed twice."]

    def test_unpunctuated_text_is_one_span(self):
        text = "no terminator here"
        assert sentence_spans(text) == [(0, len(text))]


@pytest.mark.invariant
class TestDeterminism:
    """Invariant 25: identical inputs must produce identical evidence."""

    def test_repeated_runs_agree(self, documents):
        def run():
            r = NumpyRetriever(TfidfSvdEmbedder(dim=16, random_state=0))
            r.index(documents)
            return [(m.doc_id, round(m.score, 6), m.span) for m in r.search("checkout failure", k=4)]

        assert run() == run()
