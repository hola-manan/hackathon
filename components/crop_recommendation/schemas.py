"""Data models for the crop recommendation engine (Component 1).

The engine takes a farm *location* and returns a ranked, explained set of crop
recommendations. Everything in between is a `FeatureVector` — the canonical,
unit-harmonised representation every model layer consumes (see
docs/component1-data-model-flow.md §4).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Season(str, Enum):
    kharif = "kharif"   # monsoon sown, Jun–Oct
    rabi = "rabi"       # winter sown, Nov–Mar
    zaid = "zaid"       # summer, Apr–May


class Irrigation(str, Enum):
    rainfed = "rainfed"
    partial = "partial"     # some borewell/canal backup
    assured = "assured"     # canal / assured irrigation


class Location(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class FeatureVector(BaseModel):
    """One harmonised feature vector for a plot × season."""
    lat: float
    lon: float
    season: Season
    agro_zone: str
    state: Optional[str] = None

    # soil (Soil Health Card native units: kg/ha, pH direct)
    soil_ph: float
    soil_n: float          # available N, kg/ha
    soil_p: float          # available P, kg/ha
    soil_k: float          # available K, kg/ha
    soil_oc: Optional[float] = None    # % organic carbon
    soil_texture: str = "loam"
    soil_source: str = "fallback"

    # climate / weather
    temp_min_c: float
    temp_max_c: float
    temp_mean_c: float
    humidity_pct: float
    seasonal_rainfall_mm: float
    rainfall_source: str = "fallback"

    # hydrology
    groundwater_depth_m: float
    groundwater_source: str = "fallback"

    # provenance — which features came from live data vs fallback
    real_features: list[str] = Field(default_factory=list)
    fallback_features: list[str] = Field(default_factory=list)

    @property
    def available_water_mm(self) -> float:
        """Effective seasonal water the crop could draw on: effective rainfall
        plus a groundwater accessibility bonus (shallower table = more usable)."""
        effective_rain = self.seasonal_rainfall_mm * 0.8
        gw_bonus = max(0.0, 150.0 - self.groundwater_depth_m * 4.0)  # mm, heuristic
        return round(effective_rain + gw_bonus, 1)


class CropScore(BaseModel):
    crop: str
    suitability: float           # L2, 0..1
    expected_yield_t_ha: float   # L3
    water_need_mm: int
    water_risk: float            # L4, 0..1 (higher = riskier)
    est_margin_rs_per_ha: int    # L4
    score: float                 # final ranking score, 0..1
    reasons: list[str]


class RecommendationResult(BaseModel):
    location: Location
    season: Season
    agro_zone: str
    state: Optional[str]
    ranked_crops: list[CropScore]
    confidence: float            # L5, 0..1
    needs_soil_test: bool
    advisory_text: str
    feature_provenance: dict     # {"real": [...], "fallback": [...]}
    model_version: str
