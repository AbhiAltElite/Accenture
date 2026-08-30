"""Looking for independent support in the company's own words.

Statistics can establish that a movement happened in a particular slice at a
particular time. They cannot tell you that customers were unable to pay. For
that the engine reads what people wrote at the time: tickets, rep notes, the
release log.

Corroboration never promotes a candidate on its own. A verified cause with
supporting tickets is better evidenced than one without, and that difference
belongs in the confidence score rather than in the verdict. Text agreeing with a
number is not proof that the number was caused by what the text describes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

import pandas as pd

from whychain.corroborate.documents import Document
from whychain.corroborate.extract import (
    RETAIL_VOCABULARY,
    Extraction,
    IssueType,
    RuleExtractor,
    Vocabulary,
    summarise,
)
from whychain.corroborate.quarantine import quarantine
from whychain.corroborate.retriever import NumpyRetriever
from whychain.evidence import (
    Evidence,
    EvidenceKind,
    EvidenceStore,
    MethodClass,
    Provenance,
    Unit,
)

if TYPE_CHECKING:
    from whychain.corroborate.extract import Extractor
    from whychain.corroborate.query import QueryWriter
    from whychain.corroborate.retriever import Retriever
    from whychain.verify.tests import Candidate

# Below this best-match score the note and the complaints it produced share
# almost no vocabulary, which is what a register mismatch looks like from here.
# Measured on the flagship cases: retail's release note tops out around 0.4
# against its own tickets, while a petroleum turnaround note reaches 0.16
# against the dealer complaints that describe its consequences.
REGISTER_FLOOR = 0.25

# Which complaints would corroborate which cause. A checkout regression should
# produce checkout complaints; if it produced only delivery complaints, the
# tickets are describing something else entirely.
RELATED_ISSUES: dict[str, tuple[str, ...]] = {
    IssueType.CHECKOUT_FAILURE: (IssueType.CHECKOUT_FAILURE, IssueType.PAYMENT_FAILURE),
    IssueType.PAYMENT_FAILURE: (IssueType.PAYMENT_FAILURE, IssueType.CHECKOUT_FAILURE),
    IssueType.DELIVERY_DELAY: (IssueType.DELIVERY_DELAY, IssueType.STOCKOUT),
    IssueType.STOCKOUT: (IssueType.STOCKOUT, IssueType.DELIVERY_DELAY),
    IssueType.PRICING: (IssueType.PRICING,),
    IssueType.QUALITY: (IssueType.QUALITY,),
    IssueType.OTHER: (),
}

# Terms that describe a cause but never appear in a customer complaint. A
# customer writes about a broken payment page, not about a release identifier.
_NOT_IN_COMPLAINTS = (
    "release", "deployment", "rollout", "competitor", "supplier", "carrier",
    "distribution centre", "sop", "process", "planning",
)


@dataclass(frozen=True)
class Corpus:
    """What a candidate's own words are expected to be echoed by, in one industry.

    Two facts, neither of them a rule: which issue codes would corroborate which
    (a checkout regression should produce checkout complaints, and if it produced
    only delivery complaints the tickets are describing something else), and
    which words belong to the operational note rather than to the people
    affected by it — a customer writes about a broken payment page, never about
    a release identifier, and a consignee writes about a container nobody will
    release, never about the tariff notification that stopped it.

    Defaults to retail's, so every existing caller behaves exactly as before.
    """

    related_issues: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(RELATED_ISSUES)
    )
    not_in_complaints: tuple[str, ...] = _NOT_IN_COMPLAINTS
    # Always a vocabulary, never None. An optional here would mean callers have
    # to remember that "unset" means "retail's", and one that forgot passed None
    # straight into the candidate scanner.
    vocabulary: Vocabulary = RETAIL_VOCABULARY

    def extractor(self) -> RuleExtractor:
        return RuleExtractor(self.vocabulary)

    def expected_for(self, subject: str) -> tuple[str, ...]:
        """Which complaint codes would corroborate a cause whose note reads like this.

        A recognised subject narrows the search, and that narrowing is the point:
        a checkout regression corroborated only by pricing complaints is not
        corroborated at all.

        An *unrecognised* subject is a different case, and treating the two alike
        was a defect. The table maps the residual to an empty tuple, and an empty
        expectation does not mean "nothing corroborates this" — it means every
        retrieved document is discarded before it is read, so corroboration can
        never be found however much of it the record holds. That is not a rare
        edge: an operational note and the complaint it produces are written in
        different registers, and in petroleum a refinery turnaround "reducing
        downstream allocation to 55 per cent of indent" shares almost no
        vocabulary with the dealer who writes "no stock at the depot since
        Monday". Every externally-caused event in petroleum and power classified
        as the residual, so every one of them reported an empty record while the
        tickets describing it sat in the retrieved set.

        With no recognised subject there is nothing to narrow with, so anything
        the vocabulary recognises counts. An extraction that is itself
        unrecognised still does not: the residual is never expected, so a ticket
        the vocabulary cannot read is set aside rather than counted as support.
        """
        related = self.related_issues.get(subject, ())
        if related:
            return related
        return tuple(issue for issue, _ in self.vocabulary.issue_terms)


RETAIL_CORPUS = Corpus()


@dataclass(frozen=True)
class Corroboration:
    """What the record says about one candidate."""

    candidate_id: str
    supporting: tuple[Extraction, ...]
    unrelated: tuple[Extraction, ...]
    flagged: tuple[Extraction, ...]      # documents containing instruction-like text
    searched: int
    # What was actually searched with. On the receipt because a reader comparing
    # a model run against a deterministic one needs to see the thing that
    # differed, and this is it.
    query: str = ""

    @property
    def support_count(self) -> int:
        return len(self.supporting)

    @property
    def summary(self) -> dict[str, int]:
        return summarise([*self.supporting, *self.unrelated])


def _complaint_query(
    description: str, not_in_complaints: tuple[str, ...] = _NOT_IN_COMPLAINTS
) -> str:
    """Turn a note about a cause into words a customer might have used.

    Two things are dropped. The leading identifier, because an event id appears
    in no ticket and dominates a short query. And internal vocabulary: nobody
    writes in to complain about a deployment, so leaving those words in pulls
    retrieval away from the complaints that would corroborate the cause.
    """
    body = description.split(":", 1)[-1] if ":" in description[:40] else description
    words = [
        w.strip(".,;")
        for w in body.lower().split()
        if len(w) > 3
        and not any(term in w for term in not_in_complaints)
        and not re.search(r"[\d_]|-\w+-", w)   # identifiers, not language
    ]
    return " ".join(words) or body


def _as_documents(tickets: pd.DataFrame) -> list[Document]:
    """Ticket rows as Documents, over column arrays rather than row objects.

    `iterrows` builds a Series per row, which costs more than everything the
    retriever then does with the result.
    """
    return [
        Document(
            doc_id=str(doc_id), source_id="voice_ops", text=str(text),
            ts=pd.Timestamp(ts).to_pydatetime().replace(tzinfo=UTC),
            metadata={"region": str(region)},
        )
        for doc_id, text, ts, region in zip(
            tickets["doc_id"], tickets["text"], tickets["ts"], tickets["region"],
            strict=True,
        )
    ]


def corroborate(
    candidate: Candidate,
    documents: pd.DataFrame,
    *,
    retriever: Retriever | None = None,
    extractor: Extractor | None = None,
    corpus: Corpus = RETAIL_CORPUS,
    k: int = 12,
    index: bool = True,
    query_writer: QueryWriter | None = None,
    domain_restriction: tuple[str, ...] = (),
) -> Corroboration:
    """Search the window for text that supports this candidate.

    Only tickets are searched. Release logs and ops notes are where candidates
    came from in the first place, and letting a candidate corroborate itself
    would turn one record into two pieces of evidence.

    Pass `index=False` with an already-indexed retriever when running many
    candidates over one corpus; refitting per candidate is the slowest thing the
    engine does and changes nothing.

    `corpus` carries the industry's own vocabulary and the words that belong to
    an operational note rather than to the people affected by it. It defaults to
    retail's, which is what every existing caller gets.
    """
    retriever = retriever or NumpyRetriever()
    extractor = extractor or corpus.extractor()

    tickets = documents[documents["doc_type"] == "support_ticket"]
    if tickets.empty:
        return Corroboration(candidate.candidate_id, (), (), (), 0)

    # What the note describing this candidate is actually about. Searching on the
    # candidate's kind alone retrieves whatever complaint type is most common in
    # the window, which is how a weather event ends up corroborated by pricing
    # complaints. Searching on what the note says retrieves what it describes.
    described = extractor.extract([
        quarantine(candidate.candidate_id, candidate.description,
                   domain_restriction=domain_restriction)
    ])
    subject = described[0].issue if described else corpus.vocabulary.residual_issue
    expected = corpus.expected_for(subject)

    # Only the retrieved handful are ever read, so the whole corpus is
    # materialised as Document objects only when this call has to index it.
    # Building seven thousand of them per candidate in order to look up twelve
    # was the slowest thing in a diagnosis, and none of it was analysis.
    if index:
        retriever.index(_as_documents(tickets))

    window = (
        datetime.combine(candidate.start, time.min, tzinfo=UTC),
        datetime.combine(candidate.end, time.max, tzinfo=UTC),
    )
    # The deterministic query is always built, and is what a model expansion is
    # added to rather than what it replaces. See `corroborate.query`: the
    # proposal is filtered to language before it gets here, retrieval below is
    # unchanged, and every document it returns still faces the extractor and the
    # verbatim citation check.
    query = _complaint_query(candidate.description, corpus.not_in_complaints)
    matches = retriever.search(query, k=k, window=window, min_score=0.15)

    # The model is used on the margin, not by default, and the margin is
    # measured rather than assumed. If the note's own words already score well
    # against some complaint, the two registers overlap and the deterministic
    # query is doing its job -- which is the ordinary case in retail, where a
    # release note saying "card entry on the Android checkout flow" and a
    # customer saying "the card bit just spins" share `card`. A weak best match
    # is the signal that they do not overlap: the event is real, the complaints
    # are there, and the note simply does not use their words. That is the case
    # worth spending a model call on, and it is what every externally-caused
    # event in petroleum and power looks like.
    #
    # Judging it on the retrieval score rather than on the extraction keeps the
    # decision cheap: retrieval is deterministic and already done, so nothing is
    # generated twice to find out whether generating was needed.
    best = max((m.score for m in matches), default=0.0)
    if query_writer is not None and best < REGISTER_FLOOR:
        query = query_writer.write(candidate.description, query)
        matches = retriever.search(query, k=k, window=window, min_score=0.15)

    text_by_id = dict(
        zip(tickets["doc_id"].astype(str), tickets["text"].astype(str), strict=True)
    )
    # Redaction happens here, before the text becomes prompt tokens, and the
    # citation check downstream runs against the redacted text -- so a model
    # cannot quote back something it was never shown.
    quarantined = [
        quarantine(m.doc_id, text_by_id[m.doc_id],
                   domain_restriction=domain_restriction)
        for m in matches
    ]
    extractions = extractor.extract(quarantined)

    supporting = tuple(e for e in extractions if e.issue in expected)
    unrelated = tuple(e for e in extractions if e.issue not in expected)
    flagged = tuple(e for e in extractions if e.flags)

    return Corroboration(
        candidate_id=candidate.candidate_id,
        supporting=supporting,
        unrelated=unrelated,
        flagged=flagged,
        searched=len(matches),
        query=query,
    )


def record_corroboration(
    corroboration: Corroboration, store: EvidenceStore, top_n: int = 4
) -> list[Evidence]:
    """Write supporting passages as evidence, each citing its own span."""
    out: list[Evidence] = []
    for extraction in corroboration.supporting[:top_n]:
        out.append(
            store.add(
                Evidence(
                    id=store.next_id(),
                    kind=EvidenceKind.CORROBORATION,
                    claim=(
                        f"A customer reported {str(extraction.issue).replace('_', ' ')}"
                        + (f" on {extraction.channel}" if extraction.channel else "")
                        + " during the window."
                    ),
                    value=None,
                    unit=Unit.NONE,
                    method="retrieval",
                    method_class=MethodClass.RETRIEVAL,
                    confidence=extraction.confidence,
                    provenance=Provenance(
                        source_id="voice_ops",
                        doc_id=extraction.doc_id,
                        span=extraction.span,
                        quote=extraction.quote,
                    ),
                    run_id=store.run_id,
                    extra={
                        "issue": str(extraction.issue),
                        "candidate_id": corroboration.candidate_id,
                        # Carried through so a reader can see the source contained
                        # instruction-like text, even though it was treated as data.
                        "injection_flags": list(extraction.flags),
                    },
                )
            )
        )
    return out
