"""Deterministic unit tests for the pipeline layers (no network).

    python -m components.crop_recommendation.tests
"""
from __future__ import annotations

from . import knowledge as kb
from . import pipeline as pl
from .schemas import FeatureVector, Season


def _fv(**over) -> FeatureVector:
    base = dict(
        lat=16.3, lon=80.4, season=Season.kharif, agro_zone="Deccan Plateau",
        soil_ph=6.6, soil_n=260, soil_p=22, soil_k=190, soil_oc=0.6,
        temp_min_c=24, temp_max_c=33, temp_mean_c=28.5, humidity_pct=60,
        seasonal_rainfall_mm=520, groundwater_depth_m=22,
        real_features=["weather+rainfall"], fallback_features=["soil", "groundwater", "ndvi"],
    )
    base.update(over)
    return FeatureVector(**base)


def test_l1_season_filter():
    fv = _fv(season=Season.rabi)
    cands = pl.l1_candidates(fv)
    assert "Rice" not in cands, "Rice is kharif-only, must not appear in rabi"
    assert "Wheat" in cands, "Wheat should be a rabi candidate"


def test_l1_arid_drops_thirsty_crops():
    fv = _fv(seasonal_rainfall_mm=230, groundwater_depth_m=38)
    cands = pl.l1_candidates(fv)
    assert "Sugarcane" not in cands, "Sugarcane infeasible under an arid water budget"
    assert "Pearl millet (Bajra)" in cands, "drought-tolerant bajra should survive"


def test_l2_ph_penalised_out_of_band():
    good = pl.l2_suitability(_fv(soil_ph=6.6), "Rice")[0]
    bad = pl.l2_suitability(_fv(soil_ph=9.0), "Rice")[0]
    assert good > bad, "an out-of-range pH must lower suitability"


def test_l4_waterrisk_rises_with_deep_groundwater():
    price = kb.CROP_KB["Rice"]["price"]
    fv_shallow = _fv(groundwater_depth_m=5, seasonal_rainfall_mm=700)
    fv_deep = _fv(groundwater_depth_m=45, seasonal_rainfall_mm=700)
    _, wr_shallow, _, _ = pl.l4_rank(fv_shallow, "Rice", 0.8, 4.0, price)
    _, wr_deep, _, _ = pl.l4_rank(fv_deep, "Rice", 0.8, 4.0, price)
    assert wr_deep > wr_shallow, "deep groundwater must increase water risk for rice"


def test_l5_confidence_low_when_soil_is_fallback():
    fv = _fv(soil_source="fallback")
    from .schemas import CropScore
    ranked = [CropScore(crop="A", suitability=.9, expected_yield_t_ha=3, water_need_mm=500,
                        water_risk=.1, est_margin_rs_per_ha=50000, score=.8, reasons=[]),
              CropScore(crop="B", suitability=.8, expected_yield_t_ha=3, water_need_mm=500,
                        water_risk=.1, est_margin_rs_per_ha=40000, score=.78, reasons=[])]
    conf, needs = pl.l5_confidence(fv, ranked)
    assert needs is True and conf < 0.6


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    main()
