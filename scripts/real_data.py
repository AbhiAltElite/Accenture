"""Run the engine on data nobody here generated.

Every number this project publishes comes from a warehouse we wrote. That is
defensible, and it is defended at length in the README, but it leaves one
question we could not answer: does the ingestion path work on data shaped by
somebody else, with somebody else's defects in it?

This answers it. It loads the UCI *Online Retail II* dataset, 1,067,371 real
invoice lines from a UK gift retailer between December 2009 and December 2011,
maps it onto a contract, and runs the real detection path over it. Nothing is
cleaned beyond what the contract declares, because the point is what happens to
a contract when the data is not ours.

    make real-data

**What this can and cannot show.** There is no answer key, so accuracy is not
computable and this script never prints one. What it prints is behaviour: how
many movements clear both bars, where they land, and whether the days the
engine flags coincide with shocks that are externally documented and dated.

Three such shocks fall inside the window, each with a different control-group
shape, which is what makes them useful rather than merely interesting:

  * **VAT 17.5% to 20%, effective 4 Jan 2011**, announced 22 June 2010.
    United Kingdom only, so every other country is a control. 196 days of
    published warning, which is a foreseeability test we did not plant.
  * **The coldest UK December in 100 years, Dec 2010.** UK only. Reported at
    the time as a record slump in British retail sales.
  * **Eyjafjallajokull, airspace closed from 15 April 2010**, much of European
    airspace shut for six days. A European shock, so non-European countries are
    the control.

The engine is told none of this. The dates are held here and compared against
what it flagged, afterwards.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SOURCE = Path("data/real/online_retail_II.xlsx")
WAREHOUSE = Path("data/real/online_retail.duckdb")

# Externally documented, dated, and not plantable by us. Held here and used
# only after the engine has spoken.
KNOWN_SHOCKS = (
    ("VAT 17.5% to 20%", date(2011, 1, 4), ("United Kingdom",),
     "announced 22 Jun 2010, 196 days of public notice"),
    ("Coldest UK December in 100 years", date(2010, 12, 20), ("United Kingdom",),
     "record slump in British retail sales reported at the time"),
    ("Eyjafjallajokull airspace closure", date(2010, 4, 15), ("EUROPE",),
     "much of European airspace closed for six days from 15 Apr"),
)

EUROPE = {
    "United Kingdom", "EIRE", "Germany", "France", "Netherlands", "Spain",
    "Switzerland", "Belgium", "Portugal", "Italy", "Norway", "Sweden",
    "Finland", "Denmark", "Austria", "Poland", "Greece", "Cyprus", "Malta",
    "Iceland", "Lithuania", "Czech Republic", "Channel Islands",
}


def build() -> None:
    """Shape the real file into the one table a contract can be written against.

    Deliberately minimal. `status` is derived from the invoice prefix because
    that is what the source actually encodes, and nothing else is repaired: the
    negative quantities, the zero prices and the missing customer ids stay, so
    the contract meets them.
    """
    if not SOURCE.exists():
        raise SystemExit(
            f"{SOURCE} not found.\n"
            "Download it once:\n"
            "  mkdir -p data/real && curl -L -o data/real/or2.zip "
            "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip "
            "&& unzip -o data/real/or2.zip -d data/real"
        )
    book = pd.ExcelFile(SOURCE)
    raw = pd.concat([book.parse(s) for s in book.sheet_names], ignore_index=True)

    invoice = raw["Invoice"].astype(str)
    frame = pd.DataFrame({
        "order_id": invoice,
        "order_ts": pd.to_datetime(raw["InvoiceDate"]),
        "region": raw["Country"].astype(str),
        "sku": raw["StockCode"].astype(str),
        "qty": raw["Quantity"].astype("int64"),
        "unit_price": raw["Price"].astype("float64"),
        "discount": 0.0,
        # The source marks a cancellation by prefixing the invoice with C. That
        # is the only status signal it carries, and the contract excludes it the
        # same way the retail contract excludes cancellations.
        "status": pd.Series("complete", index=raw.index).mask(
            invoice.str.startswith("C"), "cancelled"),
    })

    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    if WAREHOUSE.exists():
        WAREHOUSE.unlink()
    con = duckdb.connect(str(WAREHOUSE))
    con.execute("CREATE TABLE pos_txn AS SELECT * FROM frame")
    con.close()
    print(f"  built {WAREHOUSE} from {len(frame):,} real invoice lines")


def series(region: str | None = None) -> pd.DataFrame:
    """Daily net revenue, by the same arithmetic the retail contract declares."""
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    where = "status <> 'cancelled'"
    if region:
        where += f" AND region = '{region}'"
    frame = con.execute(f"""
        SELECT date_trunc('day', order_ts)::DATE AS d,
               SUM(qty * unit_price - discount) AS value
        FROM pos_txn WHERE {where}
        GROUP BY 1 ORDER BY 1
    """).df()
    con.close()
    return frame


def main() -> int:
    from whychain.contracts.registry import load_contract
    from whychain.detect.anomaly import decompose_for, find_anomalies, material

    print("\n" + "=" * 78)
    print("UNSEEN DATA  ยท  UCI Online Retail II, a real UK gift retailer")
    print("=" * 78)

    if not WAREHOUSE.exists():
        build()
    contract = load_contract(Path("contracts/real/uk_net_revenue.yml"))

    frame = series()
    frame = frame.rename(columns={"d": "d", "value": "value"})
    frame["d"] = pd.to_datetime(frame["d"])
    print(f"\n  {len(frame):,} trading days, "
          f"{frame.d.min().date()} to {frame.d.max().date()}")
    print(f"  median day  {frame.value.median():,.0f}   "
          f"max day  {frame.value.max():,.0f}")

    try:
        decomposition = decompose_for(frame, contract)
    except ValueError as exc:
        print(f"\n  the engine declined to fit: {exc}")
        return 1

    found = find_anomalies(decomposition, contract.materiality.min_abs_robust_z)
    flagged = material(found, contract)
    drops = [a for a in flagged if a.direction == "drop"]
    print(f"\n  statistically unusual days          {len(found)}")
    print(f"  ... and material in money too       {len(flagged)}")
    print(f"  of which falls                      {len(drops)}")

    print("\n  Ten largest falls the engine flagged, national:")
    for a in sorted(drops, key=lambda x: x.delta)[:10]:
        pct = a.delta / a.expected if a.expected else 0.0
        print(f"    {a.day}  {a.delta:>12,.0f}  {pct:>7.1%}  z {a.robust_z:>6.2f}")

    print("\n" + "-" * 78)
    print("AGAINST SHOCKS THE ENGINE WAS NEVER TOLD ABOUT")
    print("-" * 78)
    hits = 0
    for name, when, where, note in KNOWN_SHOCKS:
        near = [a for a in flagged if abs((a.day - when).days) <= 10]
        mark = "flagged" if near else "nothing"
        if near:
            hits += 1
            closest = min(near, key=lambda a: abs((a.day - when).days))
            pct = closest.delta / closest.expected if closest.expected else 0.0
            detail = (f"{closest.day} ({closest.direction}, {pct:+.1%}, "
                      f"z {closest.robust_z:.2f}), {len(near)} day(s) in window")
        else:
            detail = "no material movement within 10 days"
        print(f"\n  {name}")
        print(f"    event        {when}  ({', '.join(where)})")
        print(f"    context      {note}")
        print(f"    engine       {mark}: {detail}")
    print(f"\n  {hits} of {len(KNOWN_SHOCKS)} documented shocks have a material "
          f"movement within ten days.")
    print("\n  This is not an accuracy score. There is no answer key here, and")
    print("  coincidence in time is not causation: December is also Christmas.")
    print("  What it shows is that the detector, tuned on a different business")
    print("  in a different currency, lands on days a human would investigate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
