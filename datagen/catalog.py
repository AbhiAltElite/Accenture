"""The business the generated data describes.

An omnichannel Indian CPG retailer. City coordinates are real because weather is
pulled from a real feed against them — an external cause the engine corroborates
has to point at something that actually happened.
"""

from __future__ import annotations

from dataclasses import dataclass

REGIONS = ("North", "South", "East", "West")
CHANNELS = ("web", "app", "store")
DEVICES = ("mobile", "desktop", "tablet", "pos")

# Devices that can exist on a given channel. A store sale has no browser, and a
# join that ignores this produces desktop orders in physical stores.
CHANNEL_DEVICES: dict[str, tuple[str, ...]] = {
    "web": ("desktop", "mobile", "tablet"),
    "app": ("mobile", "tablet"),
    "store": ("pos",),
}


@dataclass(frozen=True)
class City:
    name: str
    region: str
    lat: float
    lon: float
    weight: float  # share of regional volume


CITIES: tuple[City, ...] = (
    City("Mumbai", "West", 19.0760, 72.8777, 0.45),
    City("Pune", "West", 18.5204, 73.8567, 0.32),
    City("Ahmedabad", "West", 23.0225, 72.5714, 0.23),
    City("Delhi", "North", 28.6139, 77.2090, 0.48),
    City("Jaipur", "North", 26.9124, 75.7873, 0.28),
    City("Lucknow", "North", 26.8467, 80.9462, 0.24),
    City("Bengaluru", "South", 12.9716, 77.5946, 0.42),
    City("Chennai", "South", 13.0827, 80.2707, 0.33),
    City("Hyderabad", "South", 17.3850, 78.4867, 0.25),
    City("Kolkata", "East", 22.5726, 88.3639, 0.62),
    City("Bhubaneswar", "East", 20.2961, 85.8245, 0.38),
)


@dataclass(frozen=True)
class Product:
    sku: str
    category: str
    base_price: float   # INR
    elasticity: float   # own-price elasticity; premium lines are less elastic
    launched_month: int = 0  # months after the series start; > 0 means sparse history


CATEGORIES = ("personal_care", "packaged_foods", "home_care", "beverages", "snacks")

PRODUCTS: tuple[Product, ...] = (
    Product("PC-1001", "personal_care", 249.0, -1.5),
    Product("PC-1002", "personal_care", 599.0, -0.9),
    Product("PC-1003", "personal_care", 149.0, -1.8),
    Product("PF-2001", "packaged_foods", 320.0, -1.2),
    Product("PF-2002", "packaged_foods", 180.0, -1.6),
    Product("HC-3001", "home_care", 210.0, -1.4),
    Product("HC-3002", "home_care", 460.0, -1.0),
    Product("BV-4001", "beverages", 90.0, -2.0),
    Product("BV-4002", "beverages", 140.0, -1.7),
    Product("SN-5001", "snacks", 60.0, -2.2),
    Product("SN-5002", "snacks", 110.0, -1.9),
    # Launched late in the window on purpose: three weeks of history is not
    # enough to build a comparison group, and the engine must say so rather
    # than manufacture confidence. This is the sparse-history scenario.
    Product("PC-1099", "personal_care", 899.0, -0.7, launched_month=35),
)


def cities_in(region: str) -> tuple[City, ...]:
    return tuple(c for c in CITIES if c.region == region)


def products_in(category: str) -> tuple[Product, ...]:
    return tuple(p for p in PRODUCTS if p.category == category)


def region_of(city_name: str) -> str:
    for city in CITIES:
        if city.name == city_name:
            return city.region
    raise KeyError(f"unknown city: {city_name}")
