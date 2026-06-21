from __future__ import annotations

from dataclasses import dataclass

SWPC_ORIGIN = "https://services.swpc.noaa.gov"


@dataclass(frozen=True)
class Endpoint:
    path: str
    family: str
    cadence_seconds: int = 60
    protection_tier: str = "minimal"


MINIMAL_PROTECTION_ENDPOINTS = [
    Endpoint("/products/noaa-scales.json", "scales"),
    Endpoint("/products/alerts.json", "alerts"),
    Endpoint("/json/rtsw/rtsw_mag_1m.json", "solar_wind_mag"),
    Endpoint("/json/rtsw/rtsw_wind_1m.json", "solar_wind"),
    Endpoint("/json/planetary_k_index_1m.json", "kp"),
    Endpoint("/products/noaa-planetary-k-index.json", "kp"),
    Endpoint("/products/noaa-planetary-k-index-forecast.json", "kp_forecast"),
    Endpoint("/json/goes/primary/xrays-6-hour.json", "xray"),
    Endpoint("/json/goes/primary/integral-protons-6-hour.json", "protons"),
]


ASSET_SPECIFIC_PROTECTION_ENDPOINTS = [
    Endpoint(
        "/json/goes/secondary/xrays-6-hour.json",
        "xray",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/goes/secondary/integral-protons-6-hour.json",
        "protons",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/goes/primary/integral-electrons-6-hour.json",
        "electrons",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/goes/secondary/integral-electrons-6-hour.json",
        "electrons",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/goes/primary/differential-electrons-6-hour.json",
        "electrons",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/goes/secondary/differential-electrons-6-hour.json",
        "electrons",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/goes/primary/magnetometers-1-day.json",
        "magnetometers",
        cadence_seconds=300,
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/json/ovation_aurora_latest.json",
        "aurora",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/products/glotec/geojson_2d_urt.json",
        "ionosphere",
        protection_tier="asset_specific",
    ),
    Endpoint(
        "/products/kyoto-dst.json",
        "dst",
        protection_tier="asset_specific",
    ),
]


SWPC_ENDPOINTS = [
    *MINIMAL_PROTECTION_ENDPOINTS,
    *ASSET_SPECIFIC_PROTECTION_ENDPOINTS,
]
