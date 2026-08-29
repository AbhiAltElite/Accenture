"""Reading candidate causes out of the operational record.

Everything the business wrote down during the window is a candidate: a release
note, a promotion, a supplier email. The engine has no way to tell which of them
mattered, and deliberately does not try at this stage. Sorting real causes from
coincidences is what verification is for, and doing it earlier by intuition is
the failure the whole design exists to avoid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from whychain.corroborate.extract import RETAIL_VOCABULARY, Vocabulary, _first_term
from whychain.verify.tests import Candidate


def _scope(text: str, vocabulary: Vocabulary = RETAIL_VOCABULARY) -> dict[str, str | None]:
    """Which slice of the business a note is about.

    Shares the extractor's vocabulary rather than keeping a second, smaller copy.
    Scope matters more than it looks: a competitor price cut described as
    affecting "personal care prices" must be tested against personal care alone.
    Measured across a whole region it is swamped by whatever else was happening,
    and a real cause gets rejected for the wrong reason.
    """
    return {
        dimension: _first_term(text, terms)
        for dimension, terms in vocabulary.scope_terms.items()
    }


def from_operations(
    documents: pd.DataFrame,
    start: date,
    end: date,
    window_days: int = 10,
    vocabulary: Vocabulary = RETAIL_VOCABULARY,
) -> list[Candidate]:
    """Candidates from release logs and operational notes."""
    if documents.empty:
        return []
    ts = pd.to_datetime(documents["ts"]).dt.date
    in_scope = documents[
        documents["doc_type"].isin(["release_log", "ops_note"])
        & (ts >= start - timedelta(days=window_days))
        & (ts <= end)
    ]

    out: list[Candidate] = []
    for _, row in in_scope.iterrows():
        text = str(row["text"])
        identifier = re.split(r"[:\s]", text, maxsplit=1)[0] or f"doc-{row['doc_id']}"
        region = row["region"]
        scope = _scope(text, vocabulary)
        out.append(
            Candidate(
                candidate_id=identifier,
                kind=row["doc_type"],
                start=pd.Timestamp(row["ts"]).date(),
                end=end,
                exposed_regions=() if region in ("All", None) else (region,),
                description=text,
                channel=scope["channel"],
                device=scope["device"],
                category=scope["category"],
            )
        )
    return out


@dataclass(frozen=True)
class PlanSpec:
    """What the weekly planning extract calls its planned interventions.

    Every industry writes down things it intends to do to some of its regions
    for some weeks, and each one is a candidate that a movement in those weeks
    might be explained by. Retail calls them promotions; a fuel marketer calls
    them refinery turnarounds and price revision cycles; a generator calls them
    outage schedules. The shape is identical -- an id, an active flag, a set of
    exposed regions -- so only the column names and the wording differ, and both
    are facts about the source system rather than about the method.

    Defaults to retail's, so every existing caller is unaffected.
    """

    id_column: str = "promo_id"
    active_column: str = "promo_active"
    kind: str = "promotion"
    noun: str = "Promotion"


RETAIL_PLAN = PlanSpec()


def from_promotions(
    plan_ops: pd.DataFrame, start: date, end: date, spec: PlanSpec = RETAIL_PLAN
) -> list[Candidate]:
    """Candidates from the weekly plan: planned interventions and competitor activity.

    One that ran in several regions arrives here with all of them attached,
    which is what later makes exposure consistency testable.
    """
    if plan_ops.empty or spec.id_column not in plan_ops.columns:
        return []
    week = pd.to_datetime(plan_ops["week"]).dt.date
    active = plan_ops[
        plan_ops[spec.active_column].fillna(False)
        & (week >= start - timedelta(days=14))
        & (week <= end)
    ]
    if active.empty:
        return []

    out: list[Candidate] = []
    for plan_id, group in active.groupby(spec.id_column):
        weeks = pd.to_datetime(group["week"]).dt.date
        categories = group["category"].unique()
        out.append(
            Candidate(
                candidate_id=str(plan_id),
                kind=spec.kind,
                start=max(min(weeks), start - timedelta(days=14)),
                end=end,
                exposed_regions=tuple(sorted(group["region"].unique())),
                description=f"{spec.noun} {plan_id} active in "
                            f"{', '.join(sorted(group['region'].unique()))}",
                category=str(categories[0]) if len(categories) == 1 else None,
            )
        )
    return out
