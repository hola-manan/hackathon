"""Feature providers for Component 1.

Each provider fetches one feature family for a lat/lon and degrades gracefully:
try a real, free/no-key source; on any failure fall back to the agro-zone
defaults in knowledge.py. Every provider records whether the value came from
live data or fallback so the engine can report provenance and adjust confidence.

Live sources used (no API key required):
  - Weather / rainfall : Open-Meteo forecast + historical archive
  - Soil               : SoilGrids REST (ISRIC)  [may be paused -> fallback]
Providers with no free API (groundwater/CGWB, market/Agmarknet, NDVI/GEE) use
documented fallbacks and expose the same interface for later wiring.
"""
from __future__ import annotations

import logging
from datetime import date

import httpx

from . import knowledge as kb
from .schemas import Season

log = logging.getLogger("kisan.c1.providers")

_TIMEOUT = httpx.Timeout(8.0)


# --------------------------------------------------------------------------- #
# Weather / rainfall — Open-Meteo (free, no key)
# --------------------------------------------------------------------------- #
class WeatherProvider:
    FORECAST = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

    async def fetch(self, lat: float, lon: float, season: Season, zone: dict) -> dict:
        out = {"source": "fallback"}
        t = zone["temp"][season]
        out.update(temp_min_c=float(t[0]), temp_max_c=float(t[1]),
                   temp_mean_c=round((t[0] + t[1]) / 2, 1),
                   humidity_pct=float(zone["humidity"]),
                   seasonal_rainfall_mm=float(zone["rain"][season]))

        # Live current conditions + short forecast for temp/humidity.
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.get(self.FORECAST, params={
                    "latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "current": "relative_humidity_2m,temperature_2m",
                    "forecast_days": 7, "timezone": "auto"})
                r.raise_for_status()
                j = r.json()
            daily = j.get("daily", {})
            tmaxs = [x for x in daily.get("temperature_2m_max", []) if x is not None]
            tmins = [x for x in daily.get("temperature_2m_min", []) if x is not None]
            if tmaxs and tmins:
                out["temp_max_c"] = round(sum(tmaxs) / len(tmaxs), 1)
                out["temp_min_c"] = round(sum(tmins) / len(tmins), 1)
                out["temp_mean_c"] = round((out["temp_max_c"] + out["temp_min_c"]) / 2, 1)
            hum = j.get("current", {}).get("relative_humidity_2m")
            if hum is not None:
                out["humidity_pct"] = float(hum)
            out["source"] = "open-meteo"
        except Exception as e:  # noqa: BLE001
            log.info("weather forecast fallback: %s", e)

        # Live seasonal rainfall from last year's same season (archive).
        try:
            start, end = kb.season_date_range(season, date.today().year - 1)
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.get(self.ARCHIVE, params={
                    "latitude": lat, "longitude": lon,
                    "start_date": start.isoformat(), "end_date": end.isoformat(),
                    "daily": "precipitation_sum", "timezone": "auto"})
                r.raise_for_status()
                precs = [x for x in r.json().get("daily", {}).get("precipitation_sum", [])
                         if x is not None]
            if precs:
                out["seasonal_rainfall_mm"] = round(sum(precs), 1)
                out["source"] = "open-meteo"
        except Exception as e:  # noqa: BLE001
            log.info("rainfall archive fallback: %s", e)

        return out


# --------------------------------------------------------------------------- #
# Soil — SoilGrids REST (ISRIC). Gap-fills Soil Health Card.
# --------------------------------------------------------------------------- #
class SoilProvider:
    URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

    async def fetch(self, lat: float, lon: float, zone: dict) -> dict:
        d = zone["soil"]
        out = {"source": "fallback", "ph": float(d["ph"]), "n": float(d["n"]),
               "p": float(d["p"]), "k": float(d["k"]), "oc": float(d["oc"]),
               "texture": d["texture"]}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.get(self.URL, params=[
                    ("lon", lon), ("lat", lat),
                    ("property", "phh2o"), ("property", "soc"),
                    ("depth", "0-5cm"), ("value", "mean")])
                r.raise_for_status()
                layers = r.json()["properties"]["layers"]
            got = {l["name"]: l["depths"][0]["values"]["mean"] for l in layers}
            if got.get("phh2o") is not None:
                out["ph"] = round(got["phh2o"] / 10.0, 1)   # SoilGrids pH is ×10
                out["source"] = "soilgrids"
            if got.get("soc") is not None:
                out["oc"] = round(got["soc"] / 100.0, 2)     # dg/kg → %
            # NOTE: SoilGrids total-N is NOT available-N; we keep zone N/P/K
            # (SHC-native) rather than mixing incompatible nitrogen units.
        except Exception as e:  # noqa: BLE001
            log.info("soilgrids fallback: %s", e)
        return out


# --------------------------------------------------------------------------- #
# Groundwater — CGWB / India-WRIS has no free API; zone fallback for now.
# --------------------------------------------------------------------------- #
class GroundwaterProvider:
    async def fetch(self, lat: float, lon: float, zone: dict) -> dict:
        return {"depth_m": float(zone["gw_depth_m"]), "source": "fallback"}


# --------------------------------------------------------------------------- #
# Market prices — Agmarknet (needs data.gov.in key); KB price used as fallback.
# --------------------------------------------------------------------------- #
class MarketProvider:
    async def price_rs_per_qtl(self, crop: str) -> tuple[float, str]:
        return float(kb.CROP_KB[crop]["price"]), "kb-fallback"


# --------------------------------------------------------------------------- #
# NDVI — Google Earth Engine (needs service account); optional proxy.
# --------------------------------------------------------------------------- #
class SatelliteProvider:
    async def ndvi(self, lat: float, lon: float, season: Season) -> tuple[float | None, str]:
        return None, "unavailable"


weather_provider = WeatherProvider()
soil_provider = SoilProvider()
groundwater_provider = GroundwaterProvider()
market_provider = MarketProvider()
satellite_provider = SatelliteProvider()
