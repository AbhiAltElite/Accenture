"""Reading candidate causes out of the operational record.

Everything the business wrote down during the window is a candidate: a release
note, a promotion, a supplier email. The engine has no way to tell which of them
mattered, and deliberately does not try at this stage. Sorting real causes from
coincidences is what verification is for, and doing it earlier by intuition is
the failure the whole design exists to avoid.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd

from whychain.verify.tests import Candidate

# Words that place a document's subject on a channel or device, so a candidate
# inherits the scope of the thing it describes.
_SCOPE_HINTS = {
    "channel": {"app": "app", "mobile app": "app", "web": "web", "store": "store"},
    "device": {"android": "mobile", "mobile": "mobile", "desktop": "desktop"},
}


def _scope(text: str) -> dict[str, str | None]:
    lowered = text.lower()
    found: dict[str, str | None] = {"channel": None, "device": None}
    for dimension, hints in _SCOPE_HINTS.items():
        for phrase, value in hints.items():
            if phrase in lowered:
                found[dimension] = value
                break
    return found


def from_operations(
    documents: pd.DataFrame, start: date, end: date, window_days: int = 10
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
        scope = _scope(text)
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
            )
        )
    return out


def from_promotions(plan_ops: pd.DataFrame, start: date, end: date) -> list[Candidate]:
    """Candidates from the weekly plan: promotions and competitor activity.

    A promotion that ran in several regions arrives here with all of them
    attached, which is what later makes exposure consistency testable.
    """
    if plan_ops.empty or "promo_id" not in plan_ops.columns:
        return []
    week = pd.to_datetime(plan_ops["week"]).dt.date
    active = plan_ops[
        plan_ops["promo_active"].fillna(False)
        & (week >= start - timedelta(days=14))
        & (week <= end)
    ]
    if active.empty:
        return []

    out: list[Candidate] = []
    for promo_id, group in active.groupby("promo_id"):
        weeks = pd.to_datetime(group["week"]).dt.date
        categories = group["category"].unique()
        out.append(
            Candidate(
                candidate_id=str(promo_id),
                kind="promotion",
                start=max(min(weeks), start - timedelta(days=14)),
                end=end,
                exposed_regions=tuple(sorted(group["region"].unique())),
                description=f"Promotion {promo_id} active in "
                            f"{', '.join(sorted(group['region'].unique()))}",
                category=str(categories[0]) if len(categories) == 1 else None,
            )
        )
    return out
