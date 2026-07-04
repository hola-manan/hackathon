"""Static agronomic knowledge base for Component 1.

Three things live here:
  1. CROP_KB   — per-crop EcoCrop/ICAR-style suitability ranges + economics.
  2. AGRO_ZONES — India agro-climatic zones with default soil/climate/hydrology
                  used as fallback when a live provider has no data.
  3. helpers   — lat/lon → zone, month → season, nutrient level thresholds.

Numbers are indicative (public agronomic references) and are meant to be
replaced by trained models / real SHC data later. See
docs/component1-crop-recommendation.md for the data-source lineage.
"""
from __future__ import annotations

from datetime import date

from .schemas import Season

# --------------------------------------------------------------------------- #
# 1 · Crop knowledge base
# --------------------------------------------------------------------------- #
# ph_*: min / opt-low / opt-high / max ; temp_* °C ; rain_* mm per season
# n/p/k_need: relative demand ; water_need_mm: crop water requirement / season
# base_yield_t_ha, price_rs_per_qtl, cost_rs_per_ha: economics
# gw_tolerance_m: deepest groundwater the crop tolerates before water-stress
CROP_KB: dict[str, dict] = {
    "Rice": dict(seasons={Season.kharif}, ph=(4.5, 5.5, 7.0, 8.0),
                 temp=(20, 25, 35, 40), rain=(900, 1200, 2000, 2500),
                 n="high", p="med", k="med", water_need_mm=1100,
                 base_yield=4.5, price=2100, cost=42000, gw_tol=6),
    "Maize": dict(seasons={Season.kharif, Season.rabi}, ph=(5.5, 6.0, 7.5, 8.0),
                  temp=(18, 21, 30, 35), rain=(500, 600, 900, 1200),
                  n="high", p="med", k="med", water_need_mm=550,
                  base_yield=5.0, price=2000, cost=35000, gw_tol=12),
    "Cotton": dict(seasons={Season.kharif}, ph=(6.0, 6.5, 8.0, 8.5),
                   temp=(21, 25, 35, 40), rain=(500, 600, 1000, 1200),
                   n="med", p="med", k="high", water_need_mm=700,
                   base_yield=2.0, price=6500, cost=48000, gw_tol=20),
    "Sorghum (Jowar)": dict(seasons={Season.kharif, Season.rabi}, ph=(6.0, 6.5, 8.0, 8.5),
                            temp=(20, 26, 33, 40), rain=(350, 450, 700, 900),
                            n="low", p="low", k="med", water_need_mm=450,
                            base_yield=3.0, price=2900, cost=22000, gw_tol=40),
    "Pearl millet (Bajra)": dict(seasons={Season.kharif}, ph=(6.5, 7.0, 8.5, 9.0),
                                 temp=(23, 27, 34, 42), rain=(300, 400, 650, 800),
                                 n="low", p="low", k="low", water_need_mm=400,
                                 base_yield=2.5, price=2500, cost=18000, gw_tol=45),
    "Groundnut": dict(seasons={Season.kharif, Season.rabi}, ph=(6.0, 6.2, 7.2, 7.5),
                      temp=(20, 25, 32, 38), rain=(500, 600, 900, 1100),
                      n="low", p="high", k="med", water_need_mm=550,
                      base_yield=2.2, price=6000, cost=40000, gw_tol=25),
    "Green gram (Moong)": dict(seasons={Season.kharif, Season.zaid}, ph=(6.2, 6.5, 7.5, 8.0),
                               temp=(22, 27, 34, 40), rain=(300, 400, 650, 800),
                               n="low", p="med", k="low", water_need_mm=350,
                               base_yield=1.0, price=7500, cost=20000, gw_tol=30),
    "Chickpea (Chana)": dict(seasons={Season.rabi}, ph=(6.0, 6.2, 7.8, 8.5),
                             temp=(10, 18, 28, 32), rain=(250, 350, 550, 700),
                             n="low", p="high", k="med", water_need_mm=350,
                             base_yield=1.5, price=5400, cost=25000, gw_tol=30),
    "Wheat": dict(seasons={Season.rabi}, ph=(6.0, 6.3, 7.5, 8.0),
                  temp=(10, 15, 25, 30), rain=(400, 500, 900, 1100),
                  n="high", p="med", k="med", water_need_mm=500,
                  base_yield=4.0, price=2300, cost=33000, gw_tol=15),
    "Mustard": dict(seasons={Season.rabi}, ph=(6.0, 6.3, 7.5, 8.0),
                    temp=(10, 15, 25, 30), rain=(250, 300, 500, 650),
                    n="med", p="high", k="low", water_need_mm=350,
                    base_yield=1.3, price=5600, cost=24000, gw_tol=25),
    "Soybean": dict(seasons={Season.kharif}, ph=(6.0, 6.3, 7.3, 7.8),
                    temp=(18, 24, 32, 36), rain=(500, 600, 1000, 1300),
                    n="low", p="high", k="med", water_need_mm=550,
                    base_yield=2.5, price=4600, cost=30000, gw_tol=20),
    "Pigeon pea (Tur)": dict(seasons={Season.kharif}, ph=(6.0, 6.5, 7.5, 8.2),
                             temp=(20, 25, 33, 38), rain=(400, 600, 1000, 1300),
                             n="low", p="med", k="med", water_need_mm=500,
                             base_yield=1.2, price=7000, cost=26000, gw_tol=35),
    "Sugarcane": dict(seasons={Season.kharif}, ph=(6.0, 6.5, 7.7, 8.5),
                      temp=(20, 26, 35, 40), rain=(1100, 1500, 2500, 3000),
                      n="high", p="med", k="high", water_need_mm=1800,
                      base_yield=80.0, price=340, cost=95000, gw_tol=8),
    "Sunflower": dict(seasons={Season.rabi, Season.zaid}, ph=(6.0, 6.5, 7.5, 8.0),
                      temp=(18, 22, 30, 35), rain=(400, 500, 800, 1000),
                      n="med", p="high", k="med", water_need_mm=500,
                      base_yield=1.5, price=6400, cost=28000, gw_tol=25),
}

# Nutrient demand → (low_threshold, high_threshold) in kg/ha for N, P, K.
NUTRIENT_THRESHOLDS = {
    "n": (240.0, 480.0),
    "p": (11.0, 25.0),
    "k": (110.0, 280.0),
}
DEMAND_LEVEL = {"low": 0, "med": 1, "high": 2}


# --------------------------------------------------------------------------- #
# 2 · India agro-climatic zones (fallback soil/climate/hydrology)
# --------------------------------------------------------------------------- #
# Rough but plausible defaults per broad zone. rainfall is per-season mm.
AGRO_ZONES: dict[str, dict] = {
    "Indo-Gangetic Plain": dict(
        soil=dict(ph=7.2, n=280, p=18, k=200, oc=0.5, texture="loam"),
        gw_depth_m=10, humidity=65,
        rain={Season.kharif: 800, Season.rabi: 120, Season.zaid: 60},
        temp={Season.kharif: (26, 35), Season.rabi: (9, 24), Season.zaid: (24, 40)}),
    "Western Dry (Arid)": dict(
        soil=dict(ph=8.1, n=180, p=12, k=240, oc=0.3, texture="sandy"),
        gw_depth_m=35, humidity=40,
        rain={Season.kharif: 350, Season.rabi: 60, Season.zaid: 20},
        temp={Season.kharif: (28, 40), Season.rabi: (10, 27), Season.zaid: (28, 44)}),
    "Deccan Plateau": dict(
        soil=dict(ph=6.8, n=250, p=16, k=190, oc=0.5, texture="clay-loam"),
        gw_depth_m=22, humidity=55,
        rain={Season.kharif: 520, Season.rabi: 110, Season.zaid: 40},
        temp={Season.kharif: (24, 34), Season.rabi: (16, 30), Season.zaid: (25, 39)}),
    "East Coast (Humid)": dict(
        soil=dict(ph=6.4, n=260, p=20, k=170, oc=0.6, texture="clay"),
        gw_depth_m=8, humidity=75,
        rain={Season.kharif: 700, Season.rabi: 300, Season.zaid: 90},
        temp={Season.kharif: (26, 34), Season.rabi: (20, 30), Season.zaid: (27, 38)}),
    "West Coast (Humid)": dict(
        soil=dict(ph=5.8, n=270, p=15, k=160, oc=0.9, texture="laterite"),
        gw_depth_m=6, humidity=80,
        rain={Season.kharif: 2200, Season.rabi: 150, Season.zaid: 80},
        temp={Season.kharif: (24, 31), Season.rabi: (22, 32), Season.zaid: (25, 34)}),
    "Eastern Humid": dict(
        soil=dict(ph=6.0, n=270, p=17, k=150, oc=0.7, texture="loam"),
        gw_depth_m=7, humidity=75,
        rain={Season.kharif: 1000, Season.rabi: 120, Season.zaid: 90},
        temp={Season.kharif: (26, 33), Season.rabi: (13, 27), Season.zaid: (25, 37)}),
    "Central Highlands": dict(
        soil=dict(ph=7.0, n=240, p=14, k=210, oc=0.5, texture="black-cotton"),
        gw_depth_m=18, humidity=55,
        rain={Season.kharif: 750, Season.rabi: 90, Season.zaid: 40},
        temp={Season.kharif: (25, 34), Season.rabi: (12, 28), Season.zaid: (26, 41)}),
    "Southern Peninsular": dict(
        soil=dict(ph=6.6, n=255, p=18, k=180, oc=0.6, texture="red-loam"),
        gw_depth_m=15, humidity=65,
        rain={Season.kharif: 500, Season.rabi: 350, Season.zaid: 120},
        temp={Season.kharif: (25, 34), Season.rabi: (21, 31), Season.zaid: (26, 38)}),
    "Generic Tropical": dict(
        soil=dict(ph=6.5, n=250, p=16, k=185, oc=0.5, texture="loam"),
        gw_depth_m=15, humidity=60,
        rain={Season.kharif: 600, Season.rabi: 150, Season.zaid: 70},
        temp={Season.kharif: (25, 34), Season.rabi: (16, 29), Season.zaid: (26, 39)}),
}


def classify_agro_zone(lat: float, lon: float) -> tuple[str, str | None]:
    """Approximate India agro-climatic zone + state guess from lat/lon.

    Bounding-box heuristics — good enough to pick sane fallback defaults; a real
    deployment swaps this for a shapefile lookup (NARP zones)."""
    if not (6 <= lat <= 37 and 68 <= lon <= 98):
        return "Generic Tropical", None

    # West coast strip
    if lon < 76 and 8 <= lat <= 21:
        return "West Coast (Humid)", None
    # East coast strip
    if lon > 79.5 and 8 <= lat <= 22 and (lat < 16 or lon > 82):
        return "East Coast (Humid)", None
    # Arid west
    if lon < 75 and 22 <= lat <= 30:
        return "Western Dry (Arid)", "Rajasthan/Gujarat"
    # Indo-Gangetic north
    if lat >= 25 and 74 <= lon <= 88:
        return "Indo-Gangetic Plain", None
    # Eastern humid
    if lon >= 84 and 20 <= lat <= 27:
        return "Eastern Humid", None
    # Southern peninsula
    if lat < 15:
        return "Southern Peninsular", None
    # Central
    if 21 <= lat < 25 and 74 <= lon <= 84:
        return "Central Highlands", "Madhya Pradesh"
    # Default interior south/central = Deccan (covers Telangana/AP/Karnataka)
    return "Deccan Plateau", None


def infer_season(on: date | None = None) -> Season:
    m = (on or date.today()).month
    if 6 <= m <= 10:
        return Season.kharif
    if m in (11, 12, 1, 2, 3):
        return Season.rabi
    return Season.zaid


def season_date_range(season: Season, year: int) -> tuple[date, date]:
    if season is Season.kharif:
        return date(year, 6, 1), date(year, 10, 31)
    if season is Season.zaid:
        return date(year, 3, 1), date(year, 5, 31)
    # rabi spans year boundary
    return date(year, 11, 1), date(year + 1, 3, 31)
