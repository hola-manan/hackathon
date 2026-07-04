"""The L1–L5 recommendation pipeline (see docs/component1-data-model-flow.md §5).

L1 EcoCrop feasibility filter   → candidate crops (safe, explainable, offline)
L2 suitability score            → how well the plot matches the crop optimum
L3 yield prior                  → expected yield from suitability × base yield
L4 economic + water-risk rank   → margin and water-risk adjusted final score
L5 confidence                   → from data provenance + score separation

Each layer is a pure function of the FeatureVector + crop KB, so any layer can
later be swapped for a trained model (XGBoost/LightGBM) without touching the
others or the response shape.
"""
from __future__ import annotations

from . import knowledge as kb
from .schemas import CropScore, FeatureVector


def _triangular(value: float, lo: float, opt_lo: float, opt_hi: float, hi: float) -> float:
    """1.0 inside the optimum band, linearly decaying to 0 at the hard bounds."""
    if value < lo or value > hi:
        return 0.0
    if opt_lo <= value <= opt_hi:
        return 1.0
    if value < opt_lo:
        return (value - lo) / max(opt_lo - lo, 1e-6)
    return (hi - value) / max(hi - opt_hi, 1e-6)


def _nutrient_match(available: float, need: str, key: str) -> float:
    lo, hi = kb.NUTRIENT_THRESHOLDS[key]
    supply = 0 if available < lo else (1 if available < hi else 2)
    want = kb.DEMAND_LEVEL[need]
    return max(0.0, 1.0 - abs(supply - want) * 0.4)


# --------------------------------------------------------------------------- #
# L1 · EcoCrop feasibility filter
# --------------------------------------------------------------------------- #
def l1_candidates(fv: FeatureVector) -> list[str]:
    out = []
    for crop, k in kb.CROP_KB.items():
        if fv.season not in k["seasons"]:
            continue
        ph_lo, _, _, ph_hi = k["ph"]
        t_lo, _, _, t_hi = k["temp"]
        r_lo, _, _, r_hi = k["rain"]
        if not (ph_lo - 0.5 <= fv.soil_ph <= ph_hi + 0.5):
            continue
        if not (t_lo - 3 <= fv.temp_mean_c <= t_hi + 3):
            continue
        # rainfall can be supplemented by irrigation, so only drop if far below
        if fv.available_water_mm < r_lo * 0.5:
            continue
        out.append(crop)
    return out


# --------------------------------------------------------------------------- #
# L2 · suitability score (swap-in seam for XGBoost)
# --------------------------------------------------------------------------- #
def l2_suitability(fv: FeatureVector, crop: str) -> tuple[float, list[str]]:
    k = kb.CROP_KB[crop]
    reasons: list[str] = []

    ph_s = _triangular(fv.soil_ph, *k["ph"])
    temp_s = _triangular(fv.temp_mean_c, *k["temp"])
    rain_s = _triangular(fv.seasonal_rainfall_mm, *k["rain"])
    n_s = _nutrient_match(fv.soil_n, k["n"], "n")
    p_s = _nutrient_match(fv.soil_p, k["p"], "p")
    k_s = _nutrient_match(fv.soil_k, k["k"], "k")
    nutrient_s = (n_s + p_s + k_s) / 3

    # weighted blend
    score = 0.22 * ph_s + 0.20 * temp_s + 0.28 * rain_s + 0.30 * nutrient_s

    if ph_s >= 0.8:
        reasons.append("soil pH ideal")
    elif ph_s < 0.4:
        reasons.append("soil pH sub-optimal")
    if rain_s >= 0.8:
        reasons.append("rainfall matches water need")
    elif fv.seasonal_rainfall_mm < k["rain"][1]:
        reasons.append("rainfall below ideal — needs irrigation")
    if nutrient_s >= 0.8:
        reasons.append("soil nutrients adequate")
    elif nutrient_s < 0.5:
        reasons.append("nutrient gap — fertiliser needed")

    return round(score, 3), reasons[:3]


# --------------------------------------------------------------------------- #
# L3 · yield prior (swap-in seam for APY/LightGBM regressor)
# --------------------------------------------------------------------------- #
def l3_expected_yield(fv: FeatureVector, crop: str, suitability: float) -> float:
    base = kb.CROP_KB[crop]["base_yield"]
    # suitability of 1.0 → full base yield; 0.5 → ~65% of base.
    factor = 0.3 + 0.7 * suitability
    return round(base * factor, 2)


# --------------------------------------------------------------------------- #
# L4 · water-risk + economic ranking
# --------------------------------------------------------------------------- #
def l4_rank(fv: FeatureVector, crop: str, suitability: float,
            exp_yield: float, price_rs_qtl: float) -> tuple[float, float, int, list[str]]:
    k = kb.CROP_KB[crop]
    reasons: list[str] = []

    # water risk: crop water need vs available water (rain + groundwater access)
    need = k["water_need_mm"]
    deficit = max(0.0, need - fv.available_water_mm)
    water_risk = min(1.0, deficit / max(need, 1))
    if fv.groundwater_depth_m > k["gw_tol"] and k["water_need_mm"] > 500:
        water_risk = min(1.0, water_risk + 0.25)
        reasons.append("deep groundwater raises water risk")
    if water_risk < 0.15:
        reasons.append("water requirement comfortably met")

    # economics: margin = yield(t/ha)*10 qtl/t * price − input cost
    revenue = exp_yield * 10 * price_rs_qtl
    margin = int(revenue - k["cost"])
    if margin > 40000:
        reasons.append("strong expected margin")

    # normalise margin to 0..1 across a plausible ₹0–120k/ha band
    margin_norm = max(0.0, min(1.0, margin / 120000))

    score = 0.5 * suitability + 0.3 * margin_norm + 0.2 * (1 - water_risk)
    return round(score, 3), round(water_risk, 2), margin, reasons[:2]


# --------------------------------------------------------------------------- #
# L5 · confidence
# --------------------------------------------------------------------------- #
def l5_confidence(fv: FeatureVector, ranked: list[CropScore]) -> tuple[float, bool]:
    # data completeness: fraction of feature families from live sources
    total = len(fv.real_features) + len(fv.fallback_features)
    completeness = len(fv.real_features) / total if total else 0.0
    # separation: gap between best and runner-up (decisive vs ambiguous)
    sep = (ranked[0].score - ranked[1].score) if len(ranked) > 1 else 0.3
    sep_norm = min(1.0, sep / 0.15)
    confidence = round(0.55 * completeness + 0.45 * sep_norm, 2)
    # A real soil test (or farmer's Soil Health Card) removes the flag.
    needs_soil_test = fv.soil_source != "farmer" or confidence < 0.5
    return confidence, needs_soil_test
