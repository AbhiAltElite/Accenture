"""The omnichannel CPG retailer: the vertical the engine was first written for.

Every vocabulary here is the module default from the stage that owns it, named
rather than redefined. That is deliberate: if this file restated the terms, the
two copies would drift and retail would start behaving differently from the way
the stage's own docstrings describe. Retail is what "no configuration" means.
"""

from __future__ import annotations

from pathlib import Path

from whychain.actions import RETAIL_DRIVERS
from whychain.corroborate import RETAIL_CORPUS
from whychain.verify.candidates import RETAIL_PLAN
from whychain.verticals.spec import RETAIL_PLAN_COLUMNS, Vertical

RETAIL = Vertical(
    id="retail",
    label="Retail CPG",
    tagline="An omnichannel Indian consumer goods retailer",
    driven_by="Mostly internal: releases, pricing, stock and marketing, "
              "with weather and competitors at the edges",
    graph_summary=(
        "Five connected metrics across three sources. Revenue is orders times average order value; orders come from sessions and conversion. A break in one shows up in the others, which is why they are read together rather than one at a time."
    ),
    contracts_dir=Path("contracts"),
    warehouse=Path("data/warehouse/whychain.duckdb"),
    ground_truth=Path("data/ground_truth/cases.json"),
    headline_kpi="net_revenue",
    dimensions={
        "region": "Region",
        "channel": "Channel",
        "device": "Device",
        "category": "Category",
        "sku": "SKU",
    },
    corpus=RETAIL_CORPUS,
    drivers=RETAIL_DRIVERS,
    plan=RETAIL_PLAN,
    plan_columns=RETAIL_PLAN_COLUMNS,
)
