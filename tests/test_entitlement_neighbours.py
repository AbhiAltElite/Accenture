"""Entitlement on every endpoint that returns a region's figures, not only two.

`diagnose` and `candidates` refused a region outside the reader's scope. The
console drew the same region's chart from `series`, its bridge from
`decomposition` and its metric table from `overview`, and none of the three took
an entitlement. So a reader entitled to South who opened West saw the page say
"Nothing was computed ... none can leak" above West's fall, its expected band
and its price/volume/mix legs. Found by clicking through the console; the audit
passed throughout, because it only asked the two endpoints that were guarded.
"""

from __future__ import annotations

import pytest

from whychain.verticals import PETROLEUM, POWER, RETAIL

ALL = (RETAIL, PETROLEUM, POWER)
WINDOW = "start=2026-08-13&end=2026-08-15"


def _client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


def _urls(vertical, region: str) -> list[str]:
    kpi = vertical.headline_kpi
    base = f"industry={vertical.id}&kpi={kpi}"
    return [
        f"/api/series?{base}&region={region}&from=2026-08-01&to=2026-08-31",
        f"/api/decomposition?{base}&region={region}&{WINDOW}",
        f"/api/candidates?{base}&region={region}&{WINDOW}",
        f"/api/diagnose?{base}&region={region}&{WINDOW}&backend=none",
        f"/api/overview?industry={vertical.id}&region={region}",
    ]


@pytest.mark.invariant
@pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
def test_every_region_endpoint_refuses_outside_scope(vertical):
    if not vertical.is_generated():
        pytest.skip(f"{vertical.id} warehouse not generated")
    client = _client()
    leaked = []
    for url in _urls(vertical, "West"):
        response = client.get(url + "&entitled=South")
        if response.status_code != 403:
            leaked.append((url, response.status_code))
            continue
        detail = response.json()["detail"]
        assert detail["requested_region"] == "West"
        assert detail["entitled_regions"] == ["South"]
        assert detail["escalate_to"]
    assert not leaked, leaked


@pytest.mark.invariant
@pytest.mark.parametrize("vertical", ALL, ids=lambda v: v.id)
def test_the_region_a_reader_holds_is_still_served(vertical):
    if not vertical.is_generated():
        pytest.skip(f"{vertical.id} warehouse not generated")
    client = _client()
    failed = [
        (url, code)
        for url in _urls(vertical, "West")
        if (code := client.get(url + "&entitled=West").status_code) != 200
    ]
    assert not failed, failed


@pytest.mark.invariant
def test_an_all_regions_total_is_only_the_readers_regions():
    """An unscoped total discloses every region in it."""
    if not RETAIL.is_generated():
        pytest.skip("retail warehouse not generated")
    client = _client()
    window = "kpi=net_revenue&from=2026-08-01&to=2026-08-31"
    everyone = client.get(f"/api/series?{window}").json()["observed"]
    south = client.get(f"/api/series?{window}&entitled=South").json()["observed"]
    south_only = client.get(f"/api/series?{window}&region=South").json()["observed"]
    assert south == south_only
    assert south != everyone

    bridge = "kpi=net_revenue&" + WINDOW
    scoped = client.get(f"/api/decomposition?{bridge}&entitled=South").json()
    regions = next(
        (c for c in scoped["contributions"] if c["dimension"] == "region"), None
    )
    assert regions is not None
    assert {s["value"] for s in regions["slices"]} == {"South"}


@pytest.mark.invariant
def test_the_scoped_overview_does_not_share_a_cache_entry_with_the_unscoped_one():
    if not RETAIL.is_generated():
        pytest.skip("retail warehouse not generated")
    client = _client()
    latest = lambda r: {k["kpi_id"]: k["latest"] for k in r.json()["kpis"]}  # noqa: E731
    everyone = latest(client.get("/api/overview"))
    south = latest(client.get("/api/overview?entitled=South"))
    again = latest(client.get("/api/overview"))
    assert everyone == again
    assert south["net_revenue"] != everyone["net_revenue"]


@pytest.mark.invariant
def test_a_regional_document_is_refused_outside_scope():
    if not RETAIL.is_generated():
        pytest.skip("retail warehouse not generated")
    client = _client()
    # TK006710 is a West checkout ticket cited by the West diagnosis.
    assert client.get("/api/document/TK006710").status_code == 200
    assert client.get("/api/document/TK006710?entitled=West").status_code == 200
    assert client.get("/api/document/TK006710?entitled=South").status_code == 403
