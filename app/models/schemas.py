"""Pydantic request/response models shared across the three component APIs."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Shared
# --------------------------------------------------------------------------- #
class Season(str, Enum):
    kharif = "kharif"   # monsoon sown (Jun–Oct)
    rabi = "rabi"       # winter sown (Oct–Mar)
    zaid = "zaid"       # summer (Mar–Jun)


class SoilProfile(BaseModel):
    n: float = Field(..., description="Available nitrogen, kg/ha")
    p: float = Field(..., description="Available phosphorus, kg/ha")
    k: float = Field(..., description="Available potassium, kg/ha")
    ph: float = Field(..., ge=0, le=14)
    organic_carbon: Optional[float] = Field(None, description="% OC")


# --------------------------------------------------------------------------- #
# 1 · Crop Recommendation
# --------------------------------------------------------------------------- #
class RecommendationRequest(BaseModel):
    plot_id: str = "demo-plot-1"
    season: Season = Season.kharif
    soil: SoilProfile
    groundwater_depth_m: float = Field(..., description="Depth to water table, metres")
    seasonal_rainfall_mm: float = Field(..., description="Forecast rainfall for the season")
    language: str = "te"


class CropScore(BaseModel):
    crop: str
    score: float
    water_need: str            # low | medium | high
    expected_margin: str       # qualitative
    reason: str


class RecommendationResponse(BaseModel):
    plot_id: str
    season: Season
    ranked_crops: list[CropScore]
    advisory_text: str
    language: str
    model_version: str


# --------------------------------------------------------------------------- #
# 2 · Advisory & Dry-Spell Alerts
# --------------------------------------------------------------------------- #
class DayForecast(BaseModel):
    day: int
    rain_mm: float
    tmax: float
    tmin: float


class AdvisoryRequest(BaseModel):
    plot_id: str = "demo-plot-1"
    crop: str = "rice"
    growth_stage: str = "vegetative"   # initial | vegetative | flowering | maturity
    soil_moisture_pct: float = Field(..., ge=0, le=100)
    forecast: list[DayForecast]
    language: str = "te"


class Alert(BaseModel):
    type: str          # irrigation | fertilizer | dryspell
    severity: str      # info | warning | critical
    message: str


class AdvisoryResponse(BaseModel):
    plot_id: str
    crop: str
    et0_mm_day: float
    crop_water_requirement_mm: float
    irrigation_recommended_mm: float
    dry_spell_days: int
    alerts: list[Alert]
    advisory_text: str
    language: str
    model_version: str


# --------------------------------------------------------------------------- #
# 3 · Crop Health Diagnosis
# --------------------------------------------------------------------------- #
class DiagnosisResponse(BaseModel):
    diagnosis_id: str
    crop: str
    disease: str
    confidence: float
    severity: str      # low | moderate | high
    treatment_steps: list[str]
    routed_to_rsk: bool
    case_id: Optional[str]
    advisory_text: str
    language: str
    model_version: str
