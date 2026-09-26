"""Who is asking, and how we know.

Two modes, chosen by `WHYCHAIN_IDENTITY`, and every record says which applied.

**proxy** is the enterprise deployment. The console sits behind a single-sign-on
proxy (oauth2-proxy, Azure App Proxy, an ingress with OIDC) that authenticates
the reader against the company's identity provider and forwards who they are in
headers the proxy itself sets. The engine trusts those headers and nothing the
browser sends: a reader's regions come from their groups, and a region
restriction the client tries to widen is replaced by the one the identity
carries.

Those headers are only believed from the proxy. Anyone who can reach the
engine directly could otherwise type `X-Forwarded-Email: cfo@...` and sign as
the finance director. So the proxy has to prove itself on every request, one
of two ways, and with neither configured the engine refuses everyone rather
than trusting anyone (B-076):

    WHYCHAIN_PROXY_SECRET     the proxy adds `X-WhyChain-Proxy-Secret: <value>`
    WHYCHAIN_TRUSTED_PROXIES  the request arrives from one of these addresses
                              or networks, e.g. `10.0.0.0/8,127.0.0.1`

Both may be set, and then both must hold.

**demo** is everything else, including the finale. The console lets the
presenter pick a named demo user, and every audit entry records
`source: "demo"`, so no signature made on a laptop can be mistaken for one made
under single sign-on.

Group convention, set in the identity provider:
    whychain:role:<role>        e.g. whychain:role:finance_director
    whychain:region:<Region>    e.g. whychain:region:South   (repeatable)
"""

from __future__ import annotations

import hmac
import ipaddress
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


def proxy_untrusted(headers: dict[str, str], client: str | None) -> str | None:
    """Why this request cannot be taken as coming from the proxy, or None if it can.

    `client` is the address the connection came from.
    """
    secret = os.environ.get("WHYCHAIN_PROXY_SECRET", "")
    networks = [n.strip() for n in os.environ.get("WHYCHAIN_TRUSTED_PROXIES", "").split(",")
                if n.strip()]
    if not secret and not networks:
        return ("single sign-on is on but the proxy is not configured to prove itself: "
                "set WHYCHAIN_PROXY_SECRET or WHYCHAIN_TRUSTED_PROXIES")
    # Compared in constant time, so the secret cannot be guessed a byte at a time.
    if secret and not hmac.compare_digest(
            headers.get("x-whychain-proxy-secret", "").encode(), secret.encode()):
        return "this request did not come through the company's single sign-on"
    if networks and not _from(client, networks):
        return "this request did not come through the company's single sign-on"
    return None


def _from(client: str | None, networks: list[str]) -> bool:
    try:
        address = ipaddress.ip_address(client or "")
    except ValueError:
        return False
    for n in networks:
        try:
            if address in ipaddress.ip_network(n, strict=False):
                return True
        except ValueError:
            continue  # a mistyped entry grants nothing
    return False


def resolve(headers: dict[str, str], client: str | None = None) -> Identity | None:
    """The reader's identity, or None in proxy mode when there is none to believe.

    `headers` is keyed in lower case; `client` is the connecting address. Under
    single sign-on the identity headers are read only once the request has
    proved it came through the proxy.
    """
    if mode() == "proxy":
        if proxy_untrusted(headers, client):
            return None
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
