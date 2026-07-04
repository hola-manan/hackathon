"""Feature assembly + harmonisation.

Turns a farm location into one canonical `FeatureVector`: classify the agro
zone (drives fallbacks), call every provider concurrently, normalise units, and
record which features are live vs fallback. This is the single contract every
model layer depends on.
"""
from __future__ import annotations

import asyncio

from . import knowledge as kb
from .providers import (groundwater_provider, satellite_provider, soil_provider,
                        weather_provider)
from .schemas import FeatureVector, Season


async def build_feature_vector(lat: float, lon: float, season: Season) -> FeatureVector:
    zone_name, state = kb.classify_agro_zone(lat, lon)
    zone = kb.AGRO_ZONES[zone_name]

    weather, soil, gw, (ndvi, ndvi_src) = await asyncio.gather(
        weather_provider.fetch(lat, lon, season, zone),
        soil_provider.fetch(lat, lon, zone),
        groundwater_provider.fetch(lat, lon, zone),
        satellite_provider.ndvi(lat, lon, season),
    )

    real, fallback = [], []
    (real if weather["source"] != "fallback" else fallback).append("weather+rainfall")
    (real if soil["source"] != "fallback" else fallback).append("soil")
    (real if gw["source"] != "fallback" else fallback).append("groundwater")
    (real if ndvi is not None else fallback).append("ndvi")

    return FeatureVector(
        lat=lat, lon=lon, season=season, agro_zone=zone_name, state=state,
        soil_ph=soil["ph"], soil_n=soil["n"], soil_p=soil["p"], soil_k=soil["k"],
        soil_oc=soil["oc"], soil_texture=soil["texture"], soil_source=soil["source"],
        temp_min_c=weather["temp_min_c"], temp_max_c=weather["temp_max_c"],
        temp_mean_c=weather["temp_mean_c"], humidity_pct=weather["humidity_pct"],
        seasonal_rainfall_mm=weather["seasonal_rainfall_mm"],
        rainfall_source=weather["source"],
        groundwater_depth_m=gw["depth_m"], groundwater_source=gw["source"],
        ndvi_recent=ndvi, ndvi_source=ndvi_src,
        real_features=real, fallback_features=fallback,
    )
