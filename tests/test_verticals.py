"""Consistency across the three industries.

Every check here exists because the same fact is written down in two places and
the two places can drift. The generator decides what a column is called and the
vertical decides what the engine looks for; the contract declares a rupee
conversion and the panel decides what a unit is actually worth. A comment asking
someone to keep them in step is not a mechanism. These are.

The retail vertical is the control in almost every case: if a change makes
retail behave differently, it has broken the thing this whole arrangement was
supposed to preserve.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from datagen.worlds import WORLDS
from whychain import verticals
from whychain.contracts import ContractRegistry
from whychain.detect.anomaly import SEASONAL_PERIODS
from whychain.verticals import PETROLEUM, POWER, RETAIL

ALL = (RETAIL, PETROLEUM, POWER)

# Where each industry's labels live. Held here rather than on the vertical: T-04
# forbids `whychain/` and `api/` from so much as naming this directory, and the
# audit enforces it with a `git grep`. The benchmark and these tests are the only
# things that may read it.
LABELS = {
    "retail": Path("data/ground_truth/cases.json"),
    "petroleum": Path("data/ground_truth/petroleum/cases.json"),
    "power": Path("data/ground_truth/power/cases.json"),
}


class TestRegistry:
    def test_retail_is_the_default(self):
        assert verticals.get(None) is RETAIL
        assert verticals.get("") is RETAIL

    def test_unknown_industry_refuses_rather_than_falling_back(self):
        """Serving one vertical's rows under another's heading is the failure."""
        with pytest.raises(verticals.UnknownVertical, match="unknown industry"):
            verticals.get("shipping")

    def test_ids_are_unique_and_addressable(self):
        assert len({v.id for v in ALL}) == len(ALL)
        for v in ALL:
            assert verticals.get(v.id) is v


@pytest.mark.invariant
class TestGeneratorAndEngineAgree:
    """Two halves of the repository naming the same columns."""

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_plan_id_and_active_columns_match_the_generator(self, vertical):
        world = WORLDS[vertical.id]
        assert vertical.plan.id_column == world.plan_id_column, (
            f"{vertical.id}: the candidate scanner looks for "
            f"{vertical.plan.id_column!r} and the generator writes "
            f"{world.plan_id_column!r}; no planned intervention would ever "
            f"become a candidate"
        )
        assert vertical.plan.active_column == world.plan_active_column

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_driver_series_columns_match_the_generator(self, vertical):
        world = WORLDS[vertical.id]
        assert set(vertical.plan_columns.levels) == {p.name for p in world.plan_levels}, (
            f"{vertical.id}: the driver series reads "
            f"{vertical.plan_columns.levels} out of plan_ops and the generator "
            f"writes {[p.name for p in world.plan_levels]}; track B would run "
            f"on nothing"
        )
        assert vertical.plan_columns.index == world.plan_index.name

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_plan_candidate_kind_maps_to_a_driver(self, vertical):
        """Otherwise a verified cause has no lever and no owner."""
        assert vertical.plan.kind in vertical.drivers.kind_to_driver, (
            f"{vertical.id}: {vertical.plan.kind!r} candidates would reach the "
            f"decision card with no driver, so every card comes back "
            f"controllable: false"
        )


@pytest.mark.invariant
class TestVocabularies:
    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_every_related_issue_is_a_real_issue_code(self, vertical):
        corpus = vertical.corpus
        vocab = corpus.extractor().vocabulary
        known = {issue for issue, _ in vocab.issue_terms} | {vocab.residual_issue}
        for subject, related in corpus.related_issues.items():
            assert subject in known, f"{vertical.id}: {subject!r} is not an issue code"
            for other in related:
                assert other in known, (
                    f"{vertical.id}: {subject!r} expects corroboration from "
                    f"{other!r}, which nothing can ever produce"
                )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_scope_terms_cover_the_three_dimensions(self, vertical):
        scope = vertical.corpus.extractor().vocabulary.scope_terms
        assert set(scope) == {"channel", "device", "category"}, (
            f"{vertical.id}: the extractor reads exactly these three and a "
            f"missing one raises rather than narrowing a candidate"
        )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_scope_terms_resolve_to_values_the_data_contains(self, vertical):
        """A term mapping to a value no row has narrows a candidate to nothing."""
        world = WORLDS[vertical.id]
        scope = vertical.corpus.extractor().vocabulary.scope_terms
        actual = {
            "channel": set(world.channel_share),
            "device": set(world.device_share),
            "category": {p.category for p in world.products},
        }
        for dimension, terms in scope.items():
            unknown = set(terms.values()) - actual[dimension]
            assert not unknown, (
                f"{vertical.id}: {dimension} terms resolve to {sorted(unknown)}, "
                f"which no row carries; a note using those words would scope a "
                f"candidate to an empty slice"
            )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_off_vocabulary_really_is_off_vocabulary(self, vertical):
        """The measurement the model comparison rests on.

        Roughly two in five event-driven complaints must use phrasing the rule
        table cannot match. A pack whose off-vocabulary accidentally contains
        its own industry's terms would make the rule extractor look better than
        it is, and the with-model contrast would stop measuring anything.
        """
        world = WORLDS[vertical.id]
        terms = [
            t.lower()
            for _, group in vertical.corpus.extractor().vocabulary.issue_terms
            for t in group
        ]
        leaked = [
            (kind, phrase, term)
            for kind, phrases in world.voices.off_vocabulary.items()
            for phrase in phrases
            for term in terms
            if term in phrase.lower()
        ]
        assert not leaked, (
            f"{vertical.id}: off-vocabulary phrasing the rule table can match: "
            f"{leaked[:3]}"
        )


@pytest.mark.invariant
class TestContracts:
    """B-017 and T-19, checked rather than reasoned about, for every vertical."""

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_contracts_load(self, vertical):
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        assert len(list(registry)) == 5

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_headline_kpi_exists_and_decomposes(self, vertical):
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        contract = registry.get(vertical.headline_kpi)
        assert contract.decomposition.method == "pvm", (
            f"{vertical.id}: the metric the console opens on cannot be "
            f"decomposed, so the landing page links to a diagnosis that refuses"
        )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_every_grain_has_seasonal_periods(self, vertical):
        """A grain with no configured rhythm would fall back to a daily default."""
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        for contract in registry:
            assert contract.grain.time in SEASONAL_PERIODS, (
                f"{vertical.id}/{contract.kpi_id} is at a '{contract.grain.time}' "
                f"grain with no seasonal periods configured (T-19)"
            )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_materiality_floor_is_reachable(self, vertical):
        """B-017's own recorded gap: a floor no movement can ever meet.

        A rate cannot move by more than one whole unit, so a floor demanding
        more than `value_per_unit_inr` is a floor nothing can clear, and the
        metric silently stops being able to flag at all.
        """
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        for contract in registry:
            if contract.grain.aggregation.value != "ratio_of_sums":
                continue
            if contract.unit.value != "ratio":
                continue          # a currency ratio has no ceiling of one
            m = contract.materiality
            assert m.min_abs_delta_inr < m.value_per_unit_inr, (
                f"{vertical.id}/{contract.kpi_id}: the floor of "
                f"{m.min_abs_delta_inr:,.0f} needs a movement of "
                f"{m.min_abs_delta_inr / m.value_per_unit_inr:.2f} whole units "
                f"on a metric that cannot exceed 1.0, so nothing can ever be "
                f"material (B-017)"
            )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_hourly_contracts_carry_an_hourly_floor(self, vertical):
        """A day's floor applied per hour asks for a movement 24 times too large."""
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        by_grain: dict[str, list[float]] = {}
        for contract in registry:
            by_grain.setdefault(contract.grain.time, []).append(
                contract.materiality.min_abs_delta_inr
            )
        if "hour" not in by_grain or "day" not in by_grain:
            pytest.skip(f"{vertical.id} has no hourly contract to compare")
        assert max(by_grain["hour"]) < min(by_grain["day"]), (
            f"{vertical.id}: an hourly floor of {max(by_grain['hour']):,.0f} is "
            f"not below the daily floor of {min(by_grain['day']):,.0f}; the "
            f"floor is compared per observation and an hour is not a day (T-19)"
        )


@pytest.mark.invariant
class TestGroundTruth:
    """T-04 holds for every vertical, not only the one it was written for."""

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_labels_exist_and_name_real_metrics(self, vertical):
        labels = LABELS[vertical.id]
        if not labels.exists():
            pytest.skip(f"{vertical.id} labels not generated")
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        known = {c.kpi_id for c in registry}
        cases = json.loads(labels.read_text())
        assert cases, f"{vertical.id} has no labelled cases"
        for case in cases:
            assert case["kpi_id"] in known, (
                f"{vertical.id}/{case['case_id']} is labelled against "
                f"{case['kpi_id']!r}, which is not one of its contracts"
            )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_planted_slices_exist_in_the_world(self, vertical):
        """An event targeting a slice nothing occupies changes nothing at all."""
        labels = LABELS[vertical.id]
        if not labels.exists():
            pytest.skip(f"{vertical.id} labels not generated")
        world = WORLDS[vertical.id]
        actual = {
            "region": set(world.regions),
            "channel": set(world.channel_share),
            "device": set(world.device_share),
            "category": {p.category for p in world.products},
            "sku": {p.sku for p in world.products},
        }
        for case in json.loads(labels.read_text()):
            for event in (*case["causes"], *case["decoys"]):
                for dim, value in event["target"].items():
                    if value is None:
                        continue
                    assert value in actual[dim], (
                        f"{vertical.id}/{case['case_id']}: event "
                        f"{event['event_id']} targets {dim}={value!r}, which no "
                        f"row carries, so it perturbs nothing"
                    )


@pytest.mark.invariant
class TestRecovery:
    """The brief's chain is driver -> lever -> action -> expected impact -> owner.

    It broke at "expected impact" for two of the three industries, because the
    recovery table held retail's four levers and nothing else. Every card in
    petroleum and power came back with the figure blank. These are the checks
    that would have caught it.
    """

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_every_controllable_lever_has_a_declared_recovery_share(self, vertical):
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        levers = {
            d.controllable_lever
            for c in registry
            for d in c.drivers
            if d.controllable_lever
        }
        missing = sorted(levers - set(vertical.recovery.share))
        assert not missing, (
            f"{vertical.id}: {missing} appear as controllable levers on a "
            f"contract but have no recovery share, so every decision card "
            f"naming one reports its expected impact as blank"
        )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_no_recovery_share_names_a_lever_no_contract_declares(self, vertical):
        """A share for a lever nothing uses is a number that will never be read."""
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        levers = {
            d.controllable_lever
            for c in registry
            for d in c.drivers
            if d.controllable_lever
        }
        stray = sorted(set(vertical.recovery.share) - levers)
        assert not stray, f"{vertical.id}: recovery shares for unused levers {stray}"

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_reversal_scenario_is_coherent(self, vertical):
        """Its lever must be priced, and its driver must exist on some contract."""
        recovery = vertical.recovery
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        assert recovery.reversal_lever in recovery.share, (
            f"{vertical.id}: the reversal scenario applies "
            f"{recovery.reversal_lever!r}, which has no declared share"
        )
        drivers = {d.id for c in registry for d in c.drivers}
        assert recovery.reversal_driver in drivers, (
            f"{vertical.id}: the reversal scenario keys on driver "
            f"{recovery.reversal_driver!r}, which no contract declares, so it "
            f"can never be available"
        )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_price_scenario_has_an_elasticity_to_use(self, vertical):
        """Otherwise it is permanently unavailable and silently so."""
        registry = ContractRegistry.from_directory(vertical.contracts_dir)
        priced = [
            d for c in registry for d in c.drivers
            if d.id == vertical.recovery.price_driver and d.elasticity_prior is not None
        ]
        assert priced, (
            f"{vertical.id}: the price scenario reads elasticity off "
            f"{vertical.recovery.price_driver!r}, which no contract declares "
            f"with an elasticity_prior"
        )

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_external_projection_includes_the_plan_candidate_kind(self, vertical):
        """A planned intervention is external pressure; retail counts promotions."""
        assert vertical.plan.kind in vertical.recovery.external_kinds, (
            f"{vertical.id}: {vertical.plan.kind!r} candidates are excluded from "
            f"the sustained-pressure projection"
        )


@pytest.mark.invariant
class TestEveryVerticalAnswers:
    """One pass down the whole pipeline for each industry.

    The unit tests all passed while `/api/candidates` raised on the power
    vertical, because an issue code is a plain string there and one serialiser
    still called `.value` on it -- a method only retail's StrEnum has. Nothing
    below the API noticed, and nothing above it was exercised. This is the
    cheapest guard against that: actually ask each industry a question.

    Skipped rather than failed when a warehouse has not been generated, because
    `make gen` builds retail alone and that is a legitimate way to work.
    """

    WINDOWS: ClassVar[dict[str, tuple[str, str, str, str]]] = {
        "retail": ("net_revenue", "checkout_conversion", "2026-08-13", "2026-08-15"),
        "petroleum": ("net_realisation", "gantry_throughput", "2026-08-13", "2026-08-15"),
        "power": ("dispatch_realisation", "dispatch_fulfilment", "2026-08-12", "2026-08-16"),
    }

    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient

        import api.main as main

        return TestClient(main.app)

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_whole_pipeline_answers(self, client, vertical):
        if not vertical.is_generated():
            pytest.skip(f"{vertical.id} warehouse not generated; run make gen-all")
        kpi, hourly, start, end = self.WINDOWS[vertical.id]
        window = f"region=West&start={start}&end={end}"
        urls = [
            f"/api/health?industry={vertical.id}",
            f"/api/kpis?industry={vertical.id}",
            f"/api/overview?industry={vertical.id}&region=West",
            f"/api/triage?industry={vertical.id}&limit=5",
            f"/api/series?industry={vertical.id}&kpi={kpi}&region=West",
            f"/api/series?industry={vertical.id}&kpi={hourly}&region=West",
            f"/api/decomposition?industry={vertical.id}&kpi={kpi}&{window}",
            f"/api/candidates?industry={vertical.id}&kpi={kpi}&{window}",
            f"/api/diagnose?industry={vertical.id}&kpi={kpi}&{window}",
            f"/api/diagnose?industry={vertical.id}&kpi={kpi}&{window}&persona=cfo",
            # A reader entitled to the region they asked about is served
            # normally. The out-of-scope case is asserted separately below,
            # because it must *not* be a 200: this line previously carried
            # `entitled=South` against a West window and expected 200, which is
            # exactly the leak it was meant to guard.
            f"/api/diagnose?industry={vertical.id}&kpi={kpi}&{window}&entitled=West",
        ]
        failed = [(u, client.get(u).status_code) for u in urls]
        failed = [(u, code) for u, code in failed if code != 200]
        assert not failed, f"{vertical.id}: {failed}"

    @pytest.mark.invariant
    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_a_region_outside_entitlement_is_refused_not_scrubbed(self, vertical):
        """Refused before anything is computed, in every industry.

        Redaction-after-computation cannot be made airtight on this shape of
        answer: the same figure appears in a contribution table, a scenario
        estimate, a narrative sentence, a validation block and a per-cause map,
        and each has to be found and removed separately. Refusing the question
        removes the class.
        """
        if not vertical.is_generated():
            pytest.skip(f"{vertical.id} warehouse not generated")
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        kpi = vertical.headline_kpi
        window = "region=West&start=2026-08-13&end=2026-08-15"
        response = client.get(
            f"/api/diagnose?industry={vertical.id}&kpi={kpi}&{window}&entitled=South"
        )
        assert response.status_code == 403, vertical.id
        detail = response.json()["detail"]
        assert detail["requested_region"] == "West"
        assert detail["entitled_regions"] == ["South"]
        assert detail["escalate_to"]
        # Nothing about the refused slice may travel in the refusal itself.
        body = response.text.replace(",", "")
        assert "26239" not in body

    @pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
    def test_the_headline_movement_reaches_a_decision(self, vertical):
        """Detection to a named owner, which is the chain the brief asks for."""
        if not vertical.is_generated():
            pytest.skip(f"{vertical.id} warehouse not generated")
        from fastapi.testclient import TestClient

        import api.main as main

        kpi, _, start, end = self.WINDOWS[vertical.id]
        body = TestClient(main.app).get(
            f"/api/diagnose?industry={vertical.id}&kpi={kpi}"
            f"&region=West&start={start}&end={end}"
        ).json()
        cards = body.get("decisions") or []
        assert cards, f"{vertical.id}: the demo window produced no decision card"
        actionable = [c for c in cards if c["controllable"]]
        assert actionable, f"{vertical.id}: no card carries a lever"
        for card in actionable:
            assert card["owner"], (
                f"{vertical.id}: {card['lever']!r} is controllable with no owner"
            )
            assert card["expected_recovery_inr_per_day"] is not None, (
                f"{vertical.id}: {card['lever']!r} reports no expected impact, "
                f"which is the link the brief names explicitly"
            )
