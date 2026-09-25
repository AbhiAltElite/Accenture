"""Who is asking, and how we know.

Two modes, chosen by `WHYCHAIN_IDENTITY`, and every record says which applied.

**proxy** is the enterprise deployment. The console sits behind a single-sign-on
proxy (oauth2-proxy, Azure App Proxy, an ingress with OIDC) that authenticates
the reader against the company's identity provider and forwards who they are in
headers the proxy itself sets. The engine trusts those headers and nothing the
browser sends: a reader's regions come from their groups, and a region
restriction the client tries to widen is replaced by the one the identity
carries. This is only safe when the engine is reachable through the proxy
alone, which is a deployment rule, stated here so it is not forgotten.

**demo** is everything else, including the finale. The console lets the
presenter pick a named demo user, and every audit entry records
`source: "demo"`, so no signature made on a laptop can be mistaken for one made
under single sign-on.

Group convention, set in the identity provider:
    whychain:role:<role>        e.g. whychain:role:finance_director
    whychain:region:<Region>    e.g. whychain:region:South   (repeatable)
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

ROLES = ("finance_director", "fpa_analyst", "area_sales_manager", "category_manager",
         "ecommerce_lead", "supply_planner", "commercial_director")

# The people a presenter can act as. Named by seat, not by person, because the
# demo has no real users and should not pretend to.
DEMO_USERS = {
    "finance.director": ("Finance Director (demo)", "finance_director"),
    "fpa.analyst": ("FP&A Analyst (demo)", "fpa_analyst"),
    "ecommerce.lead": ("E-commerce Lead (demo)", "ecommerce_lead"),
    "category.manager": ("Category Manager (demo)", "category_manager"),
    "asm.west": ("Area Sales Manager, West (demo)", "area_sales_manager"),
}
DEFAULT_DEMO_USER = "fpa.analyst"


@dataclass(frozen=True)
class Identity:
    id: str
    name: str
    role: str
    regions: tuple[str, ...] | None  # None: no restriction carried
    source: str                      # "proxy" or "demo"

    def as_dict(self) -> dict:
        out = asdict(self)
        out["regions"] = list(self.regions) if self.regions is not None else None
        return out


def mode() -> str:
    return "proxy" if os.environ.get("WHYCHAIN_IDENTITY", "").lower() == "proxy" else "demo"


def _header(headers: dict[str, str], *names: str) -> str:
    for n in names:
        if headers.get(n):
            return headers[n].strip()
    return ""


def resolve(headers: dict[str, str]) -> Identity | None:
    """The reader's identity, or None in proxy mode when the proxy sent none.

    `headers` is keyed in lower case.
    """
    if mode() == "proxy":
        email = _header(headers, "x-forwarded-email", "x-auth-request-email")
        user = _header(headers, "x-forwarded-preferred-username", "x-forwarded-user",
                       "x-auth-request-user")
        if not (email or user):
            return None
        groups = [g.strip() for g in _header(
            headers, "x-forwarded-groups", "x-auth-request-groups").split(",") if g.strip()]
        role = next((g.split(":", 2)[2] for g in groups
                     if g.startswith("whychain:role:")), "fpa_analyst")
        regions = tuple(g.split(":", 2)[2] for g in groups if g.startswith("whychain:region:"))
        return Identity(id=email or user, name=user or email, role=role,
                        regions=regions or None, source="proxy")

    key = _header(headers, "x-whychain-user") or DEFAULT_DEMO_USER
    name, role = DEMO_USERS.get(key, DEMO_USERS[DEFAULT_DEMO_USER])
    return Identity(id=key if key in DEMO_USERS else DEFAULT_DEMO_USER,
                    name=name, role=role, regions=None, source="demo")


def effective_entitlement(identity: Identity | None, requested: str | None) -> str | None:
    """The `entitled` value a request may use.

    Under single sign-on the identity's regions win outright: a client cannot
    ask for more than its groups grant. With no region groups, or in demo mode,
    the requested value stands, which can only ever narrow what is shown.
    """
    if identity is not None and identity.source == "proxy" and identity.regions:
        return ",".join(identity.regions)
    return requested
