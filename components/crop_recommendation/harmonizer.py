"""Feature assembly + harmonisation for Component 1.

FUNCTIONALITY: turn a farm location (+ optional farmer-supplied soil/groundwater)
into one canonical `FeatureVector`. Classifies the agro-climatic zone (drives
fallbacks), calls every operational provider concurrently, and records which
feature families are live vs regional-estimate so the engine can report
provenance and set confidence honestly.
"""
from __future__ import annotations

import asyncio

from . import knowledge as kb
from .providers import (groundwater_provider, soil_provider, weather_provider)
from .schemas import FeatureVector, Season


async def build_feature_vector(
    lat: float, lon: float, season: Season,
    soil_override: dict | None = None, groundwater_m: float | None = None,
) -> FeatureVector:
    zone_name, state = kb.classify_agro_zone(lat, lon)
    zone = kb.AGRO_ZONES[zone_name]

    weather, soil, gw = await asyncio.gather(
        weather_provider.fetch(lat, lon, season, zone),
        soil_provider.fetch(zone, soil_override),
        groundwater_provider.fetch(zone, groundwater_m),
    )

    # A family counts as "real" only if it came from live data or the farmer.
    real, fallback = [], []
    for name, src in (("weather+rainfall", weather["source"]),
                      ("soil", soil["source"]),
                      ("groundwater", gw["source"])):
        (real if src not in ("fallback", "regional-estimate") else fallback).append(name)

    return FeatureVector(
        lat=lat, lon=lon, season=season, agro_zone=zone_name, state=state,
        soil_ph=soil["ph"], soil_n=soil["n"], soil_p=soil["p"], soil_k=soil["k"],
        soil_oc=soil["oc"], soil_texture=soil["texture"], soil_source=soil["source"],
        temp_min_c=weather["temp_min_c"], temp_max_c=weather["temp_max_c"],
        temp_mean_c=weather["temp_mean_c"], humidity_pct=weather["humidity_pct"],
        seasonal_rainfall_mm=weather["seasonal_rainfall_mm"],
        rainfall_source=weather["source"],
        groundwater_depth_m=gw["depth_m"], groundwater_source=gw["source"],
        real_features=real, fallback_features=fallback,
    )
