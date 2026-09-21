"""A filter has to narrow what is considered, not only what is drawn.

The console can now ask about one channel or one device. The risk that came
with it is specific: an app-only release regression is a real, verified,
well-evidenced cause that could not possibly have moved the store channel, and
an engine that keeps testing it against a store-channel movement will sometimes
pass it and print a confident false answer.

These tests pin the gate that prevents that, and the one property that makes it
safe to have: unrecorded scope is not excluded.
"""

from __future__ import annotations

from datetime import date

import pytest

from whychain.verify import filter_relevant, touches_scope
from whychain.verify.tests import Candidate


def candidate(**kw) -> Candidate:
    base = {
        "candidate_id": "rel-4.05",
        "kind": "internal_bug",
        "start": date(2026, 8, 12),
        "end": date(2026, 8, 16),
        "exposed_regions": ("West",),
        "description": "Release 4.05 broke card entry on the Android checkout flow.",
    }
    return Candidate(**{**base, **kw})


def test_a_candidate_confined_to_one_channel_is_not_relevant_to_another():
    app_only = candidate(channel="app", device="mobile")
    verdict = touches_scope(app_only, {"channel": "store"})
    assert not verdict.relevant
    # The reason is rendered to the reader, so it has to name both sides.
    assert "app" in verdict.reason
    assert "store" in verdict.reason


def test_a_candidate_in_the_asked_for_channel_stays():
    app_only = candidate(channel="app", device="mobile")
    assert touches_scope(app_only, {"channel": "app"}).relevant
    assert touches_scope(app_only, {"channel": "app", "device": "mobile"}).relevant


def test_one_mismatched_dimension_is_enough_to_set_it_aside():
    app_only = candidate(channel="app", device="mobile")
    assert not touches_scope(app_only, {"channel": "app", "device": "desktop"}).relevant


def test_unrecorded_scope_is_missing_information_not_irrelevance():
    """The property that keeps this gate from quietly deleting real causes.

    Most candidates come out of free text, and the extractor records a channel
    only when the note names one. Treating "not recorded" as "not here" would
    set aside the majority of the operational record the moment a reader touched
    a filter, and the page would look calmer for exactly the wrong reason.
    """
    unscoped = candidate(channel=None, device=None)
    assert touches_scope(unscoped, {"channel": "store", "device": "pos"}).relevant


def test_no_slice_excludes_nothing():
    app_only = candidate(channel="app")
    assert touches_scope(app_only, {}).relevant
    assert touches_scope(app_only, None).relevant


@pytest.mark.parametrize("asked,kept", [("app", True), ("store", False)])
def test_filter_relevant_reports_what_it_set_aside(asked, kept):
    """Set aside, never dropped: the reader is told what was ruled out and why."""
    found, aside = filter_relevant(
        [candidate(channel="app", device="mobile")],
        date(2026, 8, 13), date(2026, 8, 15),
        "West", {"channel": asked},
    )
    assert bool(found) is kept
    assert bool(aside) is not kept
    if aside:
        _, reason = aside[0]
        assert "store" in reason
