"""Feature providers for Component 1 (crop recommendation).

FUNCTIONALITY: fetch each feature family for a farm lat/lon from an operational,
no-key source, degrading gracefully to a documented fallback. Only sources that
actually work without paid/complex credentials are wired here:

  - WeatherProvider    : Open-Meteo (live temp/humidity) + NASA POWER
                         (seasonal-rainfall climatology). Both free, no key.
  - SoilProvider       : regional agro-zone estimate + optional farmer override.
                         (SoilGrids REST was removed: slow ~14s and returns
                         null at many points; real path is Soil Health Card.)
  - GroundwaterProvider: farmer-reported depth if given, else regional average.
                         (CGWB/India-WRIS has no free REST API.)
  - MarketProvider     : REAL mandi prices from data.gov.in Agmarknet, with the
                         KB price as fallback.

Removed vs the first cut: SoilGrids live REST (unreliable) and the GEE/NDVI
satellite stub (needs a service account; was unused in scoring).
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

from . import knowledge as kb
from .schemas import Season

log = logging.getLogger("kisan.c1.providers")

_TIMEOUT = httpx.Timeout(12.0)
_DATAGOV_KEY = os.environ.get(
    "DATAGOV_API_KEY", "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b")

_DAYS_IN_MONTH = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
_SEASON_MONTHS = {
    Season.kharif: ["JUN", "JUL", "AUG", "SEP", "OCT"],
    Season.rabi: ["NOV", "DEC", "JAN", "FEB", "MAR"],
    Season.zaid: ["APR", "MAY"],
}
_MONTH_NUM = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
              "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


# --------------------------------------------------------------------------- #
# Weather / rainfall — Open-Meteo (temp/humidity) + NASA POWER (seasonal rain)
# --------------------------------------------------------------------------- #
class WeatherProvider:
    OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
    NASA_POWER = "https://power.larc.nasa.gov/api/temporal/climatology/point"

    async def fetch(self, lat: float, lon: float, season: Season, zone: dict) -> dict:
        # Start from agro-zone fallback so we always return a full vector.
        t = zone["temp"][season]
        out = {"source": "fallback",
               "temp_min_c": float(t[0]), "temp_max_c": float(t[1]),
               "temp_mean_c": round((t[0] + t[1]) / 2, 1),
               "humidity_pct": float(zone["humidity"]),
               "seasonal_rainfall_mm": float(zone["rain"][season])}
        got_live = False

        # Live current temp/humidity + short forecast (Open-Meteo, no key).
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.get(self.OPEN_METEO, params={
                    "latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "current": "relative_humidity_2m", "forecast_days": 7,
                    "timezone": "auto"})
                r.raise_for_status()
                j = r.json()
            daily = j.get("daily", {})
            tmax = [x for x in daily.get("temperature_2m_max", []) if x is not None]
            tmin = [x for x in daily.get("temperature_2m_min", []) if x is not None]
            if tmax and tmin:
                out["temp_max_c"] = round(sum(tmax) / len(tmax), 1)
                out["temp_min_c"] = round(sum(tmin) / len(tmin), 1)
                out["temp_mean_c"] = round((out["temp_max_c"] + out["temp_min_c"]) / 2, 1)
            hum = j.get("current", {}).get("relative_humidity_2m")
            if hum is not None:
                out["humidity_pct"] = float(hum)
            got_live = True
        except Exception as e:  # noqa: BLE001
            log.info("open-meteo fallback: %s", e)

        # Seasonal rainfall from NASA POWER climatology (reliable, no key).
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                r = await c.get(self.NASA_POWER, params={
                    "parameters": "PRECTOTCORR", "community": "AG",
                    "latitude": lat, "longitude": lon, "format": "JSON"})
                r.raise_for_status()
                monthly = r.json()["properties"]["parameter"]["PRECTOTCORR"]
            total = sum(monthly[m] * _DAYS_IN_MONTH[_MONTH_NUM[m]]
                        for m in _SEASON_MONTHS[season] if monthly.get(m) is not None)
            if total > 0:
                out["seasonal_rainfall_mm"] = round(total, 1)
                got_live = True
        except Exception as e:  # noqa: BLE001
            log.info("nasa-power fallback: %s", e)

        if got_live:
            out["source"] = "open-meteo+nasa-power"
        return out


# --------------------------------------------------------------------------- #
# Soil — regional agro-zone estimate + optional farmer override
# --------------------------------------------------------------------------- #
class SoilProvider:
    async def fetch(self, zone: dict, override: dict | None = None) -> dict:
        d = zone["soil"]
        out = {"source": "regional-estimate", "ph": float(d["ph"]),
               "n": float(d["n"]), "p": float(d["p"]), "k": float(d["k"]),
               "oc": float(d["oc"]), "texture": d["texture"]}
        if override:  # values from a farmer's Soil Health Card, entered via chat
            out.update({k: v for k, v in override.items() if v is not None})
            out["source"] = "farmer"
        return out


# --------------------------------------------------------------------------- #
# Groundwater — farmer-reported borewell depth, else regional average
# --------------------------------------------------------------------------- #
class GroundwaterProvider:
    async def fetch(self, zone: dict, override_m: float | None = None) -> dict:
        if override_m is not None:
            return {"depth_m": float(override_m), "source": "farmer"}
        return {"depth_m": float(zone["gw_depth_m"]), "source": "regional-estimate"}


# --------------------------------------------------------------------------- #
# Market prices — REAL Agmarknet daily mandi prices via data.gov.in
# --------------------------------------------------------------------------- #
class MarketProvider:
    """Real Agmarknet mandi prices via data.gov.in — but the data.gov.in
    endpoint is slow (~15s/call), so we NEVER call it in the recommendation hot
    path. Instead `refresh()` populates a cache out-of-band (startup task /
    nightly batch) and `get_cached_price()` reads it instantly, falling back to
    the KB price until the cache is warm. Prices are 'as of last refresh'."""
    URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    _CACHE_TTL = 12 * 3600.0  # mandi prices refresh at most daily

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, tuple[float, str]]] = {}

    def get_cached_price(self, crop: str) -> tuple[float, str]:
        """Instant, no network — cached Agmarknet price or KB fallback."""
        import time
        cached = self._cache.get(crop)
        if cached and (time.time() - cached[0]) < self._CACHE_TTL:
            return cached[1]
        return float(kb.CROP_KB[crop]["price"]), "kb-fallback"

    async def refresh(self, crops: list[str] | None = None, per_call_timeout: float = 8.0) -> int:
        """Populate the price cache from Agmarknet. Run out-of-band. Returns the
        number of crops for which a live price was fetched."""
        import time
        crops = crops or list(kb.AGMARKNET_COMMODITY)
        results = await asyncio.gather(
            *[self._fetch_one(c, per_call_timeout) for c in crops],
            return_exceptions=True)
        hits = 0
        for crop, res in zip(crops, results):
            if isinstance(res, tuple):
                self._cache[crop] = (time.time(), res)
                hits += 1
        return hits

    async def _fetch_one(self, crop: str, timeout: float) -> tuple[float, str] | None:
        commodity = kb.AGMARKNET_COMMODITY.get(crop)
        if not commodity:
            return None
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(self.URL, params={
                "api-key": _DATAGOV_KEY, "format": "json", "limit": 20,
                "filters[commodity]": commodity})
            r.raise_for_status()
            recs = r.json().get("records", [])
        prices = [float(x["modal_price"]) for x in recs
                  if x.get("modal_price") not in (None, "", "0")]
        return (round(sum(prices) / len(prices), 0), "agmarknet") if prices else None


weather_provider = WeatherProvider()
soil_provider = SoilProvider()
groundwater_provider = GroundwaterProvider()
market_provider = MarketProvider()
