"""Component 1 engine — recommend crops from a farm location.

    result = await recommend_from_location(lat, lon)         # season auto-inferred
    result = await recommend_from_location(lat, lon, season=Season.rabi, top_n=3)

Orchestrates: location → FeatureVector (harmonizer) → L1..L5 (pipeline) →
ranked, explained RecommendationResult. Pure Python + async provider calls;
no framework dependency, so it is reusable from the API, a batch job, or a CLI.
"""
from __future__ import annotations

from . import knowledge as kb
from . import pipeline as pl
from .harmonizer import build_feature_vector
from .providers import market_provider
from .schemas import CropScore, Location, RecommendationResult, Season

MODEL_VERSION = "c1-crop-reco-v0.2-location"


async def recommend_from_location(
    lat: float, lon: float, season: Season | None = None, top_n: int = 3,
) -> RecommendationResult:
    season = season or kb.infer_season()
    fv = await build_feature_vector(lat, lon, season)

    # L1 — feasibility filter
    candidates = pl.l1_candidates(fv)

    # L2–L4 — score, yield, rank each candidate
    scored: list[CropScore] = []
    for crop in candidates:
        suitability, s_reasons = pl.l2_suitability(fv, crop)
        exp_yield = pl.l3_expected_yield(fv, crop, suitability)
        price, _ = await market_provider.price_rs_per_qtl(crop)
        score, water_risk, margin, r_reasons = pl.l4_rank(
            fv, crop, suitability, exp_yield, price)
        scored.append(CropScore(
            crop=crop, suitability=suitability, expected_yield_t_ha=exp_yield,
            water_need_mm=kb.CROP_KB[crop]["water_need_mm"], water_risk=water_risk,
            est_margin_rs_per_ha=margin, score=score,
            reasons=(s_reasons + r_reasons)[:4]))

    scored.sort(key=lambda c: c.score, reverse=True)
    top = scored[:top_n]

    # L5 — confidence
    confidence, needs_soil_test = (pl.l5_confidence(fv, scored)
                                   if scored else (0.0, True))

    advisory = _narrate(fv, top, confidence, needs_soil_test)

    return RecommendationResult(
        location=Location(lat=lat, lon=lon), season=season,
        agro_zone=fv.agro_zone, state=fv.state, ranked_crops=top,
        confidence=confidence, needs_soil_test=needs_soil_test,
        advisory_text=advisory,
        feature_provenance={"real": fv.real_features, "fallback": fv.fallback_features},
        model_version=MODEL_VERSION,
    )


def _narrate(fv, top, confidence, needs_soil_test) -> str:
    if not top:
        return ("No suitable crop found for this location and season. "
                "Please consult your nearest Rythu Seva Kendra.")
    best = top[0]
    txt = (f"For the {fv.season.value} season in the {fv.agro_zone} "
           f"(rainfall ~{fv.seasonal_rainfall_mm:.0f} mm, soil pH {fv.soil_ph}), "
           f"the best fit is {best.crop} — {', '.join(best.reasons[:2])}. ")
    if len(top) > 1:
        txt += f"Also consider {', '.join(c.crop for c in top[1:])}. "
    txt += (f"Expected yield ~{best.expected_yield_t_ha} t/ha, "
            f"estimated margin ₹{best.est_margin_rs_per_ha:,}/ha. ")
    if needs_soil_test:
        txt += "A soil test would improve this advice. "
    if confidence < 0.5:
        txt += "Confidence is low — an RSK officer can confirm."
    return txt
