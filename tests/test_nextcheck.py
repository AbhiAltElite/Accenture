"""The sentence an analyst gets on the days there is no answer.

An abstention that only says "unknown" wastes the hour as surely as a wrong
answer does, so the next check is the most useful sentence the product writes.
It was three template branches; the model now writes it under the same contract
as everything else it writes here, and this is the contract.

The gate is what is tested. A model being helpful about a movement nobody has
explained is exactly where a plausible suggestion becomes a stated cause in
somebody's retelling, so most of these are about refusing.
"""

from __future__ import annotations

import pytest

from whychain.narrate.nextcheck import MAX_WORDS, NextCheck, propose, validate

ALLOWED = frozenset({
    "rel-4.05", "west", "north", "net_revenue", "pos_txn", "finance_ledger",
    "ecommerce_lead", "finance_director",
})
FACTS = '{"worst_residual": 0.391, "coverage": 0.12}'

RESULT = {
    "kpi_id": "net_revenue",
    "region": "North",
    "verdict": "contradicted",
    "window": {"from": "2026-06-10", "to": "2026-06-12"},
    "abstention": {
        "coverage": 0.0,
        "ruled_out": [],
        "blocking": ["the two systems disagree"],
        "next_check": "reconcile net_revenue against finance_ledger for this window",
    },
    "reconciliation": {"state": "contradicted"},
}


class TestItRefusesToExplain:
    """The one thing this sentence may never do."""

    @pytest.mark.parametrize("sentence", [
        "The fall was caused by rel-4.05 rolling out early.",
        "Revenue dropped due to the release regression in West.",
        "rel-4.05 is the cause; roll it back.",
        "The gap is attributable to a missing channel.",
    ])
    def test_a_sentence_that_asserts_a_cause_is_dropped(self, sentence):
        why = validate(sentence, ALLOWED, FACTS)
        assert "asserts a cause" in why

    def test_saying_something_was_ruled_out_is_allowed(self):
        """Reporting the test result is not reviving the candidate."""
        assert not validate(
            "Confirm with the ecommerce_lead why rel-4.05 was ruled out here.",
            ALLOWED, FACTS,
        )


class TestItRefusesToInvent:
    def test_a_system_this_run_does_not_contain(self):
        why = validate(
            "Pull the Salesforce pipeline report and compare against Workday.",
            ALLOWED, FACTS,
        )
        assert "Salesforce" in why and "Workday" in why

    def test_an_identifier_this_run_does_not_contain(self):
        why = validate(
            "Compare orders_v2 against the source to see whether rows dropped.",
            ALLOWED, FACTS,
        )
        assert "orders_v2" in why

    def test_ordinary_english_is_not_an_invention(self):
        """The first version checked every word against the run's vocabulary and
        rejected "shipped", "request" and "re-running", so almost nothing could
        pass. An invention is a name, and a name looks like one."""
        assert not validate(
            "Confirm whether rel-4.05 shipped to other regions before re-running.",
            ALLOWED, FACTS,
        )

    def test_a_figure_that_is_not_in_the_facts(self):
        why = validate("Check the feed; revenue fell 32.5 per cent.", ALLOWED, FACTS)
        assert "does not appear in the facts" in why

    def test_a_figure_that_is_in_the_facts_is_allowed(self):
        """A blanket ban was the first rule and it was wrong: the template it
        replaces cites the residual, and that is the useful part of it."""
        assert not validate(
            "Reconcile net_revenue against finance_ledger; the gap is 0.391.",
            ALLOWED, FACTS,
        )

    def test_a_candidate_id_carrying_digits_is_not_arithmetic(self):
        assert not validate("Ask whether rel-4.05 reached West.", ALLOWED, FACTS)


class TestTheShape:
    def test_an_empty_answer_is_a_rejection(self):
        assert validate("   ", ALLOWED, FACTS)

    def test_too_long_is_a_rejection(self):
        assert f"{MAX_WORDS} words" in validate(
            " ".join(["check"] * (MAX_WORDS + 5)), ALLOWED, FACTS
        )


class TestItNeverMakesTheAnswerWorse:
    """Every failure path hands back the deterministic sentence."""

    def test_no_backend_uses_the_template(self):
        out = propose(RESULT, fallback="do the thing", backend=None)
        assert out == NextCheck(text="do the thing", writer="template")

    def test_a_failing_backend_uses_the_template_and_says_so(self):
        class Broken:
            name, backend, available = "fake", "fake", True

            def complete(self, **_):
                raise RuntimeError("429")

        out = propose(RESULT, fallback="do the thing", backend=Broken())
        assert out.text == "do the thing" and out.fell_back
        assert "RuntimeError" in out.rejected

    def test_a_rejected_sentence_uses_the_template_and_keeps_the_cost(self):
        """A run that spent tokens and threw the output away still spent them."""
        import json as _json

        from whychain.llm import Completion

        class Inventing:
            name, backend, available = "fake", "fake", True

            def complete(self, **_):
                return Completion(
                    text=_json.dumps({"next_check": "Pull the Salesforce report."}),
                    model="fake", tokens_in=100, tokens_out=20, backend="fake",
                )

        out = propose(
            RESULT, fallback="do the thing", backend=Inventing(),
            extra_terms=ALLOWED,
        )
        assert out.text == "do the thing"
        assert out.writer == "model -> template"
        assert "Salesforce" in out.rejected
        assert out.model_calls == 1 and out.tokens_in == 100

    def test_a_good_sentence_survives(self):
        import json as _json

        from whychain.llm import Completion

        class Good:
            name, backend, available = "fake", "fake", True

            def complete(self, **_):
                return Completion(
                    text=_json.dumps({
                        "next_check":
                            "Verify the net_revenue extract for North is complete."
                    }),
                    model="fake", tokens_in=100, tokens_out=20, backend="fake",
                )

        out = propose(
            RESULT, fallback="do the thing", backend=Good(), extra_terms=ALLOWED
        )
        assert out.writer == "model" and not out.fell_back
        assert out.text.startswith("Verify the net_revenue extract")
