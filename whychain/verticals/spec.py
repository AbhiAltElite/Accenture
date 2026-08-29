"""What distinguishes one industry from another, held as data.

The engine's methods do not vary by industry and none of them are here. What is
here is the vocabulary each industry uses for the same things: which words in an
operational note name which driver, which complaint codes would corroborate
which cause, what the planning extract calls a planned intervention, and where
that industry's contracts and warehouse live.

The separation matters for a reason the repository already argues elsewhere. A
threshold, a conversion or a seasonal period that is right for one metric and
wrong for another is T-19, and a *vocabulary* compiled into an analysis stage is
the same mistake in a different currency: it makes the stage silently correct
for the industry it was written against and silently useless for any other. A
note reading "berth window missed, vessel still on outer anchorage" describes a
delivery problem in exactly the way "courier never showed" does, and only the
phrasing differs. Phrasing is a fact about the business.

Every field defaults to retail's, so a caller that asks for nothing gets exactly
the behaviour the engine had before this module existed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from whychain.actions import RETAIL_DRIVERS, DriverMap
from whychain.corroborate import RETAIL_CORPUS, Corpus
from whychain.verify.candidates import RETAIL_PLAN, PlanSpec


@dataclass(frozen=True)
class PlanColumns:
    """What the weekly planning extract carries, for the driver series.

    `levels` are quantities and are summed over a week; `index` is a reading and
    is averaged, because the mean of a week of index readings is an index and
    their sum is nothing. These names have to match what the generator writes
    into `plan_ops` for this industry, and a test asserts that they do rather
    than a comment asking someone to remember.
    """

    levels: tuple[str, ...] = ("marketing_spend", "planned_stock")
    index: str = "competitor_price_index"


RETAIL_PLAN_COLUMNS = PlanColumns()


@dataclass(frozen=True)
class Vertical:
    """One industry the console can be pointed at.

    `dimensions` maps the engine's column names to what a reader of this
    industry calls them. The columns themselves do not change: `region`,
    `channel`, `device`, `category` and `sku` are the dimensional skeleton every
    stage is written against, and renaming them in the data would mean rewriting
    the engine rather than configuring it. So a marketing region is stored in
    `region` and displayed as "Marketing region", and the label travels with the
    vertical rather than being hard-coded in the console.
    """

    id: str
    label: str
    tagline: str
    contracts_dir: Path
    warehouse: Path
    ground_truth: Path
    headline_kpi: str
    # What moves this industry's metrics, in one phrase, for the switcher.
    driven_by: str
    # How the five metrics relate, in the reader's own vocabulary. Hard-coding
    # retail's identity in the console would tell a petroleum reader that
    # revenue is orders times average order value, which is true of a different
    # business.
    graph_summary: str = ""
    dimensions: dict[str, str] = field(default_factory=dict)
    corpus: Corpus = RETAIL_CORPUS
    drivers: DriverMap = RETAIL_DRIVERS
    plan: PlanSpec = RETAIL_PLAN
    plan_columns: PlanColumns = RETAIL_PLAN_COLUMNS

    def label_for(self, dimension: str) -> str:
        return self.dimensions.get(dimension, dimension.replace("_", " ").capitalize())

    def is_generated(self) -> bool:
        """Whether this vertical's warehouse has been built yet."""
        return self.warehouse.exists()
