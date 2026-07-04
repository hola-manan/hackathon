"""Component 1 — Smart Crop Recommendation Engine.

Demo implementation is a transparent agronomic scoring model (a stand-in for
the production XGBoost/LightGBM ranker). It scores a small crop knowledge base
against the plot's soil NPK/pH, groundwater depth, season and forecast
rainfall, returning a ranked list with a human-readable reason for each — the
"why" that builds farmer trust. Swap `_score_crop` for a trained model without
touching the API or the response shape.
"""
from __future__ import annotations

from app.models.schemas import CropScore, RecommendationRequest, RecommendationResponse, Season

MODEL_VERSION = "crop-reco-agronomic-v0.1"

# Compact agronomic knowledge base. Ranges are indicative (ICAR/EcoCrop style).
# water: relative crop water demand; ph_lo/ph_hi: suitable soil pH band.
_CROPS = [
    # name        seasons                     water   ph_lo ph_hi  n_need p_need k_need  rain_lo rain_hi  gw_tolerance_m
    ("Rice",       {Season.kharif},            "high",  5.0, 7.5,   "high", "med", "med",  900, 2500, 6),
    ("Maize",      {Season.kharif, Season.rabi}, "medium", 5.5, 7.5, "high", "med", "med", 500, 1200, 12),
    ("Cotton",     {Season.kharif},            "medium", 6.0, 8.0,  "med",  "med", "high", 500, 1000, 20),
    ("Pearl millet (Bajra)", {Season.kharif},  "low",   6.5, 8.5,  "low",  "low", "low",  300,  700, 40),
    ("Sorghum (Jowar)", {Season.kharif, Season.rabi}, "low", 6.0, 8.5, "low", "low", "med", 350, 800, 40),
    ("Groundnut",  {Season.kharif, Season.rabi}, "low",  6.0, 7.5,  "low",  "high", "med", 500, 1000, 25),
    ("Green gram (Moong)", {Season.kharif, Season.zaid}, "low", 6.2, 7.5, "low", "med", "low", 300, 700, 30),
    ("Chickpea (Chana)", {Season.rabi},        "low",   6.0, 8.0,  "low",  "high", "med", 250, 600, 30),
    ("Wheat",      {Season.rabi},              "medium", 6.0, 7.5,  "high", "med", "med", 400, 1100, 15),
    ("Mustard",    {Season.rabi},              "low",   6.0, 7.5,  "med",  "high", "low", 250, 600, 25),
]

_LEVEL = {"low": 0, "med": 1, "medium": 1, "high": 2}


def _need_ok(available: float, need: str, thresholds=(240, 480)) -> float:
    """Reward when soil supply meets the crop's demand level (0..1)."""
    lo, hi = thresholds
    supply = 0 if available < lo else (1 if available < hi else 2)
    want = _LEVEL[need]
    return max(0.0, 1.0 - abs(supply - want) * 0.4)


def _score_crop(req: RecommendationRequest, crop) -> tuple[float, str, str, str]:
    (name, seasons, water, ph_lo, ph_hi, n_need, p_need, k_need,
     rain_lo, rain_hi, gw_tol) = crop

    if req.season not in seasons:
        return 0.0, water, "n/a", "not suited to this season"

    reasons = []
    score = 0.0

    # pH suitability (0..1) weighted 0.20
    if ph_lo <= req.soil.ph <= ph_hi:
        score += 0.20
        reasons.append("soil pH in range")
    else:
        score += 0.05
        reasons.append("soil pH sub-optimal")

    # Nutrient match weighted 0.25 (N,P,K)
    n = _need_ok(req.soil.n, n_need)
    p = _need_ok(req.soil.p, p_need, thresholds=(15, 30))
    k = _need_ok(req.soil.k, k_need, thresholds=(140, 280))
    score += 0.25 * (n + p + k) / 3

    # Rainfall vs crop water band weighted 0.30
    if rain_lo <= req.seasonal_rainfall_mm <= rain_hi:
        score += 0.30
        reasons.append("rainfall matches water need")
    elif req.seasonal_rainfall_mm < rain_lo:
        deficit = (rain_lo - req.seasonal_rainfall_mm) / rain_lo
        score += max(0.0, 0.30 - deficit * 0.30)
        if water == "high":
            reasons.append("rainfall too low for a thirsty crop")
        else:
            reasons.append("some irrigation may be needed")
    else:
        score += 0.20
        reasons.append("ample rainfall")

    # Groundwater: deep water table penalises high-water crops. Weighted 0.25
    if req.groundwater_depth_m <= gw_tol:
        score += 0.25
        reasons.append("groundwater within reach")
    else:
        over = min(1.0, (req.groundwater_depth_m - gw_tol) / gw_tol)
        score += max(0.0, 0.25 - over * 0.25)
        if water != "low":
            reasons.append("deep groundwater — prefer low-water crop")

    margin = {"low": "stable", "medium": "good", "high": "high but input-heavy"}[water]
    return round(score, 3), water, margin, ", ".join(reasons[:3])


def recommend(req: RecommendationRequest) -> RecommendationResponse:
    scored = []
    for crop in _CROPS:
        s, water, margin, reason = _score_crop(req, crop)
        if s <= 0:
            continue
        scored.append(CropScore(crop=crop[0], score=s, water_need=water,
                                expected_margin=margin, reason=reason))
    scored.sort(key=lambda c: c.score, reverse=True)
    top = scored[:3]

    if top:
        best = top[0]
        advisory = (
            f"For the {req.season.value} season on your plot, the best fit is "
            f"{best.crop} ({best.reason}). "
            f"Also consider {', '.join(c.crop for c in top[1:])}. "
        )
        if req.groundwater_depth_m > 20 and best.water_need != "low":
            advisory += "Groundwater is deep, so plan supplemental irrigation carefully."
    else:
        advisory = "No suitable crop found for the given season and soil; please consult your RSK."

    return RecommendationResponse(
        plot_id=req.plot_id,
        season=req.season,
        ranked_crops=top,
        advisory_text=advisory,
        language=req.language,
        model_version=MODEL_VERSION,
    )
