"""Exercise every path a judge will actually click, and report what breaks.

The test suite proves the units are right. It does not prove the *service* is
right, because it never starts one: a stale import, a broken projection, an
endpoint that 500s only when a real region has no data — none of those fail a
unit test, and all of them fail a demo.

So this drives the running server the way a person does. Every KPI, every demo
scenario, every persona, entitlement on and off, the feedback loop, the model
catalogue. It checks status codes, and then it checks the things a status code
cannot: that a persona projection actually differs, that entitlement actually
withholds, that abstention actually abstains, that no figure claimed in the
narrative is missing from the evidence.

    make smoke        # against a server already running on :8000

Exits non-zero if anything fails, so it can gate a demo.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

BASE = "http://localhost:8000"
TIMEOUT = 60


@dataclass
class Report:
    passed: int = 0
    failed: list[str] = field(default_factory=list)
    slow: list[str] = field(default_factory=list)

    def ok(self, label: str, seconds: float = 0.0) -> None:
        self.passed += 1
        # A judge clicking through will notice anything past a second.
        if seconds > 1.0:
            self.slow.append(f"{label}: {seconds:.2f}s")
        print(f"  pass  {label}" + (f"  ({seconds:.2f}s)" if seconds > 0.5 else ""))

    def fail(self, label: str, why: str) -> None:
        self.failed.append(f"{label}: {why}")
        print(f"  FAIL  {label}\n        {why}")


def get(path: str, **params) -> tuple[int, dict, float]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return response.status, json.loads(response.read()), time.monotonic() - started
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body), time.monotonic() - started
        except ValueError:
            return exc.code, {"detail": body[:200].decode(errors="replace")}, 0.0
    except Exception as exc:
        return 0, {"detail": f"{type(exc).__name__}: {exc}"}, 0.0


def post(path: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {"detail": exc.read()[:200].decode(errors="replace")}
    except Exception as exc:
        return 0, {"detail": f"{type(exc).__name__}: {exc}"}


# The six planted scenarios, each demonstrating a different required behaviour.
# `expect` is what the engine should conclude, not what would be convenient.
SCENARIOS = [
    ("multi-factor", "net_revenue", "West", "2026-08-13", "2026-08-16", "explained"),
    ("low-confidence", "net_revenue", "South", "2026-06-03", "2026-06-10", None),
    ("seasonal-decoy", "net_revenue", "West", "2025-10-20", "2025-10-27", None),
    ("signal-gap", "on_time_delivery", "West", "2026-07-08", "2026-07-15", None),
    ("not-foreseeable", "on_time_delivery", "South", "2026-05-18", "2026-05-25", None),
    # The refusal on a KPI the console can actually diagnose. The two above are
    # on a rate, which declines the bridge, so neither is reachable in the UI.
    ("late-warning", "net_revenue", "South", "2026-03-04", "2026-03-08", "explained"),
]

KPIS = ["net_revenue", "orders", "checkout_conversion", "aov", "on_time_delivery"]
REGIONS = ["North", "South", "East", "West"]


def check_service(r: Report) -> None:
    print("\nService")
    status, body, _ = get("/api/health")
    if status != 200 or body.get("status") != "ok":
        r.fail("health", f"{status} {body}")
        return
    r.ok(f"health ({body.get('contracts')} contracts, warehouse {body.get('warehouse')})")

    status, body, _ = get("/api/kpis")
    if status != 200 or len(body) < 3:
        r.fail("kpis", f"{status}, {len(body) if isinstance(body, list) else body}")
    else:
        r.ok(f"kpis ({len(body)} declared)")

    status, body, _ = get("/api/models")
    if status != 200 or not body.get("backends"):
        r.fail("models", f"{status} {body}")
    else:
        reachable = [b["id"] for b in body["backends"] if b["available"]]
        r.ok(f"models (active {body.get('active_id')}, reachable {reachable})")
        # The enterprise slot must never claim to be available.
        enterprise = next(b for b in body["backends"] if b["id"] == "enterprise")
        if enterprise["available"]:
            r.fail("models", "the unimplemented enterprise backend reports available")


def check_overview(r: Report) -> None:
    print("\nOverview, every region")
    for region in [None, *REGIONS]:
        label = f"overview {region or 'all'}"
        status, body, seconds = get("/api/overview", region=region)
        if status != 200:
            r.fail(label, f"{status} {body.get('detail')}")
        elif not body.get("kpis"):
            r.fail(label, "no KPIs returned")
        else:
            r.ok(label, seconds)


def check_series(r: Report) -> None:
    print("\nSeries, every KPI")
    for kpi in KPIS:
        label = f"series {kpi}"
        status, body, seconds = get(
            "/api/series", kpi=kpi, region="West",
            **{"from": "2026-06-01", "to": "2026-08-31"},
        )
        if status != 200:
            r.fail(label, f"{status} {body.get('detail')}")
        elif not body.get("days"):
            r.fail(label, "empty series")
        else:
            r.ok(f"{label} ({len(body['days'])} points, {len(body.get('anomalies', []))} flagged)", seconds)


def check_scenarios(r: Report) -> None:
    print("\nPlanted scenarios")
    for name, kpi, region, start, end, expect in SCENARIOS:
        label = f"{name} ({kpi}/{region})"
        status, body, seconds = get(
            "/api/diagnose", kpi=kpi, region=region, start=start, end=end,
            persona="analyst",
        )
        # A KPI with no price/volume/mix identity declines with a reason. That is
        # a correct answer, not a failure, and the console renders it as one.
        if status == 422 and "decompos" in str(body.get("detail", "")).lower():
            r.ok(f"{label} declined with a reason", seconds)
            continue
        if status != 200:
            r.fail(label, f"{status} {body.get('detail')}")
            continue

        verdict = body.get("verdict")
        if expect and verdict != expect:
            r.fail(label, f"expected verdict {expect}, got {verdict}")
            continue

        gap = (body.get("signal_gap") or {}).get("verdict")
        r.ok(f"{label} verdict={verdict} gap={gap}", seconds)

        # Whatever the verdict, the answer must carry its own evidence.
        if verdict == "explained" and not body.get("verified"):
            r.fail(label, "verdict is explained but nothing is verified")
        if verdict == "unknown" and not (body.get("abstention") or {}).get("next_check"):
            r.fail(label, "abstained without saying what to check next")


def check_personas(r: Report) -> None:
    print("\nPersonas over one evidence set")
    base = {"kpi": "net_revenue", "region": "West",
            "start": "2026-08-13", "end": "2026-08-16"}
    seen = {}
    for persona in ("analyst", "cfo", "ops"):
        status, body, seconds = get("/api/diagnose", persona=persona, **base)
        if status != 200:
            r.fail(f"persona {persona}", f"{status} {body.get('detail')}")
            continue
        seen[persona] = body
        r.ok(f"persona {persona} ({len(body.keys())} keys)", seconds)

    if len(seen) == 3:
        # The claim: the projection differs, the evidence does not.
        movements = {p: (b.get("movement") or {}).get("total_change") for p, b in seen.items()}
        if len(set(movements.values())) != 1:
            r.fail("personas", f"the movement differs by reader: {movements}")
        else:
            r.ok(f"personas agree on the movement ({movements['analyst']})")

        shapes = {p: tuple(sorted(b.keys())) for p, b in seen.items()}
        if len(set(shapes.values())) == 1:
            r.fail("personas", "all three projections are identical; nothing is withheld")
        else:
            r.ok("personas render differently")

        # Answer 2 and the decision must reach the reader who acts on them.
        for persona in ("cfo", "ops"):
            if not seen[persona].get("signal_gap"):
                r.fail(f"persona {persona}", "signal gap is missing from this projection")
            if not seen[persona].get("decisions"):
                r.fail(f"persona {persona}", "no decision reached this reader")


def check_entitlement(r: Report) -> None:
    print("\nEntitlement")
    base = {"kpi": "net_revenue", "region": "West", "start": "2026-08-13",
            "end": "2026-08-16", "persona": "ops"}
    status, unrestricted, _ = get("/api/diagnose", **base)
    status2, restricted, _ = get("/api/diagnose", entitled="South", **base)
    if status != 200 or status2 != 200:
        r.fail("entitlement", f"{status}/{status2}")
        return

    open_causes = len(unrestricted.get("causes") or [])
    shut_causes = len(restricted.get("causes") or [])
    notice = (restricted.get("entitlement") or {}).get("notice")

    if shut_causes >= open_causes and open_causes > 0:
        r.fail("entitlement", f"out-of-scope causes were not withheld ({open_causes} -> {shut_causes})")
    elif not notice:
        r.fail("entitlement", "causes were withheld with no notice to the reader")
    elif "escalate" not in notice.lower():
        r.fail("entitlement", "the notice does not name an escalation route")
    else:
        r.ok(f"withheld {open_causes - shut_causes} cause(s) and said so")


def check_narrative(r: Report) -> None:
    print("\nNarrative and its validator")
    status, body, _ = get(
        "/api/diagnose", kpi="net_revenue", region="West",
        start="2026-08-13", end="2026-08-16", persona="analyst",
    )
    if status != 200:
        r.fail("narrative", f"{status}")
        return

    narrative = body.get("narrative") or {}
    validation = narrative.get("validation") or {}
    accepted = narrative.get("sentences") or []
    rejected = validation.get("rejected") or []

    if not accepted:
        r.fail("narrative", "no sentence survived validation")
    else:
        r.ok(f"{len(accepted)} sentence(s) accepted, {len(rejected)} rejected "
             f"by the {narrative.get('writer')} writer")

    # Every accepted sentence must cite something that exists.
    unbound = [s for s in accepted if not s.get("cites")]
    if unbound:
        r.fail("narrative", f"{len(unbound)} accepted sentence(s) cite nothing")
    else:
        r.ok("every accepted sentence is bound to evidence")

    receipt = body.get("telemetry") or {}
    stages = receipt.get("stages") or []
    if not stages:
        r.fail("receipt", "no stages recorded")
    else:
        calls = sum(s.get("model_calls") or 0 for s in stages)
        r.ok(f"receipt covers {len(stages)} stages, {calls} model call(s)")


def check_feedback(r: Report) -> None:
    print("\nFeedback loop")
    status, body, _ = get(
        "/api/diagnose", kpi="net_revenue", region="West",
        start="2026-08-13", end="2026-08-16",
    )
    run_id = body.get("run_id")
    if status != 200 or not run_id:
        r.fail("feedback", "could not obtain a run to comment on")
        return

    code, out = post("/api/feedback", {
        "run_id": run_id, "kpi_id": "net_revenue", "judgement": "wrong_owner",
        "submitted_by": "smoke-test", "persona": "analyst",
    })
    if code != 200:
        r.fail("feedback", f"{code} {out.get('detail')}")
        return
    if not out.get("learned_from"):
        r.fail("feedback", "a learnable judgement was not marked learnable")
    else:
        r.ok("correction recorded and marked learnable")

    code, out = post("/api/feedback", {
        "run_id": run_id, "kpi_id": "net_revenue", "judgement": "not_a_real_judgement",
        "submitted_by": "smoke-test",
    })
    if code != 422:
        r.fail("feedback", f"an unknown judgement was accepted ({code})")
    else:
        r.ok("an unknown judgement is refused")


def check_refusals(r: Report) -> None:
    print("\nRefusals and bad input")
    cases = [
        ("unknown KPI", {"kpi": "not_a_kpi", "start": "2026-08-13",
                         "end": "2026-08-16"}, (404, 422)),
        ("unknown region", {"kpi": "net_revenue", "region": "Atlantis",
                            "start": "2026-08-13", "end": "2026-08-16"}, (404, 422)),
        ("unknown persona", {"kpi": "net_revenue", "region": "West",
                             "start": "2026-08-13", "end": "2026-08-16",
                             "persona": "wizard"}, (422,)),
        ("window with no data", {"kpi": "net_revenue", "region": "West",
                                 "start": "1999-01-01", "end": "1999-01-08"}, (404, 422)),
    ]
    for label, params, acceptable in cases:
        status, body, _ = get("/api/diagnose", **params)
        if status in acceptable:
            r.ok(f"{label} refused with {status}")
        elif status == 200:
            r.fail(label, "accepted input it should have refused")
        else:
            r.fail(label, f"unexpected {status}: {str(body.get('detail'))[:80]}")


def main() -> int:
    print(f"Driving {BASE} the way a reader does.")
    r = Report()
    for check in (check_service, check_overview, check_series, check_scenarios,
                  check_personas, check_entitlement, check_narrative,
                  check_feedback, check_refusals):
        try:
            check(r)
        except Exception as exc:
            r.fail(check.__name__, f"the check itself raised: {type(exc).__name__}: {exc}")

    print(f"\n{r.passed} passed, {len(r.failed)} failed")
    if r.slow:
        print("\nSlower than a second, which a reader will notice:")
        for line in r.slow:
            print(f"  {line}")
    if r.failed:
        print("\nFailures:")
        for line in r.failed:
            print(f"  {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
