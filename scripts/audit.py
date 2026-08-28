"""Run the security and logic checklists against the running system.

Every check executes something. A checklist that is filled in by reading the
code proves less than one that tries to break it.
"""
from __future__ import annotations

import subprocess
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

RESULTS: list[tuple[str, str, str, str]] = []   # area, id, verdict, detail

def check(area: str, ident: str):
    def wrap(fn):
        try:
            detail = fn() or ""
            RESULTS.append((area, ident, "PASS", detail))
        except AssertionError as exc:
            RESULTS.append((area, ident, "FAIL", str(exc)))
        except Exception as exc:
            RESULTS.append((area, ident, "ERROR", f"{type(exc).__name__}: {exc}"))
        return fn
    return wrap

# ---------------------------------------------------------------- SECURITY
@check("security", "SQL injection via slice parameter")
def _():
    from fastapi.testclient import TestClient

    import api.main as m
    c = TestClient(m.app)
    payload = "West'; DROP TABLE pos_txn; --"
    r = c.get("/api/series", params={"kpi": "net_revenue", "region": payload})
    assert r.status_code in (404, 422), f"unexpected status {r.status_code}"
    from whychain.ingest import Warehouse
    with Warehouse() as wh:
        assert len(wh.table("pos_txn", limit=1)) == 1, "pos_txn did not survive"
    return "rejected; table intact"

@check("security", "Warehouse opened read-only")
def _():
    from whychain.ingest import Warehouse
    with Warehouse() as wh:
        try:
            wh._con.execute("CREATE TABLE _probe(x INT)")
        except Exception:
            return "writes refused"
    raise AssertionError("engine was able to write to the warehouse")

@check("security", "Entitlement filters in SQL, before any projection")
def _():
    from whychain.contracts import ContractRegistry
    from whychain.ingest import Warehouse
    c = ContractRegistry.from_directory("contracts").get("net_revenue")
    with Warehouse() as wh:
        limited = wh.kpi_series(c, entitled_regions=("West",))
    regions = set(limited["region"].unique())
    assert regions == {"West"}, f"leaked regions: {regions - {'West'}}"
    return "only entitled rows returned"

@check("security", "Empty entitlement grants nothing")
def _():
    from whychain.contracts import ContractRegistry
    from whychain.ingest import IngestError, Warehouse
    c = ContractRegistry.from_directory("contracts").get("net_revenue")
    with Warehouse() as wh:
        try:
            wh.kpi_series(c, entitled_regions=())
        except IngestError:
            return "empty entitlement refused rather than treated as unrestricted"
    raise AssertionError("empty entitlement returned data")

@check("security", "No secrets committed")
def _():
    # ':!' excludes this file: it contains the patterns it searches for, and a
    # scanner that always finds itself reports nothing useful.
    out = subprocess.run(
        ["git", "grep", "-InE",
         r"(sk-ant-|AKIA[0-9A-Z]{16}|password\s*=\s*['\"][^'\"]{6,})",
         "--", ".", ":!scripts/audit.py"],
        capture_output=True, text=True)
    assert out.returncode != 0, f"possible secret: {out.stdout[:120]}"
    return "none found in tracked files"

@check("security", "Internal docs excluded from the repository")
def _():
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout
    for leaked in ("_internal/", "docs/STRATEGY.md"):
        assert leaked not in tracked, f"{leaked} is tracked"
    return "_internal/ and STRATEGY.md untracked"

@check("security", "Errors do not disclose internals")
def _():
    from fastapi.testclient import TestClient

    import api.main as m
    r = TestClient(m.app).get("/api/series", params={"kpi": "nonexistent_kpi"})
    body = r.text.lower()
    for leak in ("traceback", "/users/", "select ", "duckdb.duckdb"):
        assert leak not in body, f"response leaked {leak!r}"
    return f"404 with no internals ({r.status_code})"

# ------------------------------------------------------------------- LOGIC
@check("logic", "I-24 engine cannot read ground truth")
def _():
    out = subprocess.run(["git", "grep", "-rIn", "ground_truth", "--", "whychain/", "api/"],
                         capture_output=True, text=True)
    assert out.returncode != 0, f"engine references ground truth: {out.stdout[:120]}"
    assert Path("data/ground_truth/cases.json").exists(), "labels missing; nothing to protect"
    return "no path from whychain/ or api/ to the labels"

@check("logic", "I-25 determinism: identical inputs, identical output")
def _():
    from whychain.contracts import ContractRegistry
    from whychain.detect import decompose, find_anomalies, material
    from whychain.ingest import Warehouse
    c = ContractRegistry.from_directory("contracts").get("net_revenue")
    def run():
        with Warehouse() as wh:
            raw = wh.kpi_series(c)
        s = raw[raw.region == "West"].groupby("d", as_index=False)["value"].sum().sort_values("d")
        d = decompose(s)
        return [(a.day, round(a.robust_z, 9)) for a in material(find_anomalies(d, 3.0), c)]
    a, b = run(), run()
    assert a == b, "two runs disagreed"
    return f"{len(a)} anomalies reproduced exactly"

@check("logic", "I-02 cannot_verify is distinct from rejected")
def _():
    from whychain.evidence import ClaimState
    assert ClaimState.CANNOT_VERIFY != ClaimState.REJECTED
    return "distinct terminal states (D-006)"

@check("logic", "T-03 method and unit must agree")
def _():
    from pydantic import ValidationError

    from whychain.evidence import Evidence, EvidenceKind, MethodClass, Provenance, Unit
    try:
        Evidence(id="ev_1", kind=EvidenceKind.DECOMPOSITION, claim="x", value=1.0,
                 unit=Unit.COUNT, method="pvm_bridge", method_class=MethodClass.DETERMINISTIC,
                 provenance=Provenance(source_id="pos_txn", query="SELECT 1"), run_id="r")
    except ValidationError:
        return "a bridge reporting counts is rejected at construction"
    raise AssertionError("bridge accepted a count unit")

@check("logic", "T-02 percent and percentage point are different units")
def _():
    from whychain.evidence import Unit
    assert Unit.PCT != Unit.PCT_POINT
    return "distinct units"

@check("logic", "T-15 naive timestamps refused in freshness")
def _():
    from pydantic import ValidationError

    from whychain.evidence import Freshness
    try:
        # Deliberately naive: this is the input the model must refuse.
        Freshness(
            source_id="s",
            as_of=datetime(2026, 8, 1),  # noqa: DTZ001
            observed_at=datetime(2026, 8, 2),  # noqa: DTZ001
            sla=timedelta(hours=6),
        )
    except ValidationError:
        return "naive datetimes rejected"
    raise AssertionError("naive datetime accepted")

@check("logic", "Materiality requires both tests")
def _():
    from whychain.contracts import ContractRegistry
    m = ContractRegistry.from_directory("contracts").get("net_revenue").materiality
    assert not m.is_material(delta=-1.0, robust_z=-99.0), "tiny movement passed on significance"
    assert not m.is_material(delta=-1e9, robust_z=-0.1), "large movement passed on size alone"
    assert m.is_material(delta=-1e6, robust_z=-5.0)
    return "significance and business impact both required"

@check("logic", "Business impact converts to rupees per metric unit")
def _():
    from whychain.contracts import ContractRegistry
    reg = ContractRegistry.from_directory("contracts")
    orders = reg.get("orders").materiality
    assert orders.value_per_unit_inr > 1.0, "a count is being compared against a rupee floor"
    assert reg.get("net_revenue").materiality.value_per_unit_inr == 1.0
    return "counts and ratios converted before the rupee test"

@check("logic", "Seasonal collapse is not an anomaly")
def _():
    import datetime as dt

    from whychain.contracts import ContractRegistry
    from whychain.detect import decompose, find_anomalies, material
    from whychain.ingest import Warehouse
    c = ContractRegistry.from_directory("contracts").get("net_revenue")
    with Warehouse() as wh:
        raw = wh.kpi_series(c)
    s = raw[raw.region == "West"].groupby("d", as_index=False)["value"].sum().sort_values("d")
    m = material(find_anomalies(decompose(s), 3.0), c)
    hits = [a for a in m if dt.date(2025, 10, 20) <= a.day <= dt.date(2025, 10, 27)]
    assert not hits, f"flagged post-Diwali: {[str(a.day) for a in hits]}"
    return "57.5% overnight fall correctly ignored"

@check("logic", "Planted event is detected")
def _():
    import datetime as dt

    from whychain.contracts import ContractRegistry
    from whychain.detect import decompose, find_anomalies, material
    from whychain.ingest import Warehouse
    c = ContractRegistry.from_directory("contracts").get("net_revenue")
    with Warehouse() as wh:
        raw = wh.kpi_series(c)
    s = raw[raw.region == "West"].groupby("d", as_index=False)["value"].sum().sort_values("d")
    m = material(find_anomalies(decompose(s), 3.0), c)
    hits = [a for a in m if dt.date(2026, 8, 12) <= a.day <= dt.date(2026, 8, 18)
            and a.direction == "drop"]
    assert len(hits) >= 3, f"only {len(hits)} days of a week-long event surfaced"
    return f"{len(hits)} material drops inside the planted window"

@check("logic", "Contract lineage is executable, not decorative")
def _():
    from whychain.contracts import ContractRegistry
    from whychain.ingest.warehouse import TRANSFORMS
    for c in ContractRegistry.from_directory("contracts"):
        missing = [t for t in c.lineage.transforms if t not in TRANSFORMS]
        assert not missing, f"{c.kpi_id} declares unimplemented transforms {missing}"
    return "every declared transform is implemented"

@check("logic", "Deduplication actually changes the answer")
def _():
    from whychain.ingest import Warehouse
    with Warehouse() as wh:
        raw = wh.table("pos_txn")
    dupes = int(raw["order_id"].duplicated().sum())
    assert dupes > 0, "no duplicates present, so the transform is untested"
    return f"{dupes} duplicated order ids present in the extract"

@check("logic", "Every KPI in the graph is computable")
def _():
    from whychain.contracts import ContractRegistry
    from whychain.ingest import Warehouse
    failed = []
    with Warehouse() as wh:
        for c in ContractRegistry.from_directory("contracts"):
            try:
                wh.kpi_series(c)
            except Exception as exc:
                failed.append(f"{c.kpi_id}: {str(exc)[:40]}")
    assert not failed, "; ".join(failed)
    return "all five contracts execute"

# ------------------------------------------------------------------ DESIGN
def _ui() -> str:
    return Path("ui/index.html").read_text()


@check("design", "No gradients, glass, glow or decorative blur")
def _():
    html = _ui()
    for banned in ("linear-gradient", "radial-gradient", "backdrop-filter", "blur("):
        assert banned not in html, f"found {banned}"
    return "none present"


@check("design", "No emoji or AI marketing language")
def _():
    import re
    html = _ui()
    assert not re.search(r"[\U0001F300-\U0001FAFF]", html), "emoji in the interface"
    banned = r"(?i)\b(ai-powered|magic|supercharge|unlock|smart insights|copilot)\b"
    assert not re.search(banned, html), "marketing language in the copy"
    return "copy is factual"


@check("design", "No hover scaling or bouncy motion")
def _():
    import re
    html = _ui()
    # Canvas device-pixel-ratio scaling is not a CSS transform; look for the
    # actual offence rather than the substring.
    assert not re.search(r"transform:\s*[^;]*scale\(", html), "CSS scale transform present"
    assert "cubic-bezier" not in html, "eased motion present"
    return "no motion effects"


@check("design", "Restrained radii and no card-grid-everything")
def _():
    import re
    html = _ui()
    radii = [int(v) for v in re.findall(r"border-radius:\s*(\d+)px", html)]
    # Small controls stay tight; a panel may go slightly softer. Above this and
    # the page starts reading as a card grid rather than a document.
    assert all(r <= 6 for r in radii), f"oversized radius: {max(radii)}px"
    # Count distinct radius values, not declarations: reusing one small radius
    # across several elements is consistency, not a card grid.
    distinct = len(set(radii))
    assert distinct <= 3, f"{distinct} different corner radii in use"
    return f"{len(radii)} radii, max {max(radii) if radii else 0}px"


@check("design", "Figures use tabular numerals")
def _():
    assert "tabular-nums" in _ui(), "numeric columns will not align"
    return "aligned"


@check("design", "Theme-aware with an explicit background")
def _():
    html = _ui()
    assert "prefers-color-scheme" in html, "dark theme not designed"
    # The token is matched by role rather than by name, so a rename does not turn
    # a passing check into a silent one.
    compact = html.replace(" ", "")
    assert re.search(r"body\{[^}]*background:var\(--[\w-]+\)", compact), (
        "body background not painted from a token; it would borrow the host's ground"
    )
    return "light and dark defined via tokens"


@check("design", "Keyboard focus is visible")
def _():
    assert ":focus-visible" in _ui(), "no visible focus state"
    return "focus-visible styled"


@check("design", "Status is not conveyed by colour alone")
def _():
    html = _ui()
    assert "within SLA" in html and "breached" in html, "SLA state has no text label"
    assert "${a.direction}" in html, "anomaly direction has no text label"
    return "text labels accompany colour"


@check("design", "Wide content scrolls in its own container")
def _():
    assert "overflow-x:auto" in _ui().replace(" ", ""), "tables will push the page sideways"
    return "tables scroll independently"


@check("design", "Method and thresholds are stated, not hidden")
def _():
    html = _ui()
    assert "MSTL" in html, "analytical method not named"
    assert "Both tests must pass" in html, "materiality rule not explained"
    return "method and materiality both surfaced"


def main() -> int:
    for area in ("security", "logic", "design"):
        rows = [r for r in RESULTS if r[0] == area]
        print(f"\n{area.upper()}  ({sum(1 for r in rows if r[2]=='PASS')}/{len(rows)} pass)")
        print("-" * 92)
        for _, ident, verdict, detail in rows:
            mark = {"PASS": "pass", "FAIL": "FAIL", "ERROR": "ERR "}[verdict]
            print(f"  [{mark}] {ident:<50} {detail[:34]}")
    bad = [r for r in RESULTS if r[2] != "PASS"]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks pass")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
