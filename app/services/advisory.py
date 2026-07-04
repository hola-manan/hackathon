"""Component 2 — Real-time Advisory & Dry-Spell Alerts.

Uses a simplified but genuine FAO-56 water-balance:
  ET0 (reference evapotranspiration, Hargreaves) -> ETc = ET0 * Kc
  irrigation = ETc(over horizon) - effective rainfall - soil-water buffer
Dry-spell = the longest run of forecast days below a rain threshold. This is
deterministic and fully runnable; the ML anomaly layer (Prophet/LightGBM)
described in the design plugs in alongside it later.
"""
from __future__ import annotations

import math

from app.models.schemas import Alert, AdvisoryRequest, AdvisoryResponse, DayForecast

MODEL_VERSION = "advisory-fao56-v0.1"

# FAO-56 single crop coefficients (mid-season), indicative.
_KC = {
    "rice": {"initial": 1.05, "vegetative": 1.10, "flowering": 1.20, "maturity": 0.90},
    "maize": {"initial": 0.30, "vegetative": 0.80, "flowering": 1.20, "maturity": 0.60},
    "cotton": {"initial": 0.35, "vegetative": 0.75, "flowering": 1.15, "maturity": 0.70},
    "wheat": {"initial": 0.40, "vegetative": 0.80, "flowering": 1.15, "maturity": 0.40},
    "_default": {"initial": 0.40, "vegetative": 0.85, "flowering": 1.10, "maturity": 0.60},
}

_DRY_DAY_MM = 2.5          # a day with < 2.5 mm counts as "dry"
_LOW_MOISTURE_PCT = 35.0    # below this soil moisture, irrigation is due


def _hargreaves_et0(tmax: float, tmin: float) -> float:
    """Hargreaves reference ET0 (mm/day). Ra is expressed in mm/day water
    equivalent (~15 for tropical India, i.e. ~37 MJ/m2/day * 0.408)."""
    tmean = (tmax + tmin) / 2
    ra_mm = 15.0
    et0 = 0.0023 * (tmean + 17.8) * math.sqrt(max(tmax - tmin, 0)) * ra_mm
    return round(max(et0, 0.0), 2)


def _longest_dry_run(forecast: list[DayForecast]) -> int:
    best = cur = 0
    for d in forecast:
        if d.rain_mm < _DRY_DAY_MM:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def advise(req: AdvisoryRequest) -> AdvisoryResponse:
    horizon = req.forecast or []
    days = len(horizon) or 1

    et0 = (sum(_hargreaves_et0(d.tmax, d.tmin) for d in horizon) / days) if horizon else 4.5
    kc = _KC.get(req.crop.lower(), _KC["_default"]).get(req.growth_stage, 0.85)
    etc_per_day = round(et0 * kc, 2)
    etc_total = round(etc_per_day * days, 1)

    effective_rain = round(sum(d.rain_mm for d in horizon) * 0.8, 1)  # 80% effective
    # Soil-water buffer: how much the current moisture cushions demand.
    buffer_mm = round((req.soil_moisture_pct / 100.0) * 40.0, 1)      # ~40mm root-zone capacity
    irrigation = round(max(0.0, etc_total - effective_rain - buffer_mm), 1)

    dry_spell = _longest_dry_run(horizon)

    alerts: list[Alert] = []
    if req.soil_moisture_pct < _LOW_MOISTURE_PCT:
        alerts.append(Alert(type="irrigation", severity="warning",
                            message=f"Soil moisture low ({req.soil_moisture_pct:.0f}%). "
                                    f"Irrigate ~{irrigation:.0f} mm within 48 hours."))
    elif irrigation > 0:
        alerts.append(Alert(type="irrigation", severity="info",
                            message=f"Plan ~{irrigation:.0f} mm irrigation over the next {days} days."))
    else:
        alerts.append(Alert(type="irrigation", severity="info",
                            message="Rainfall covers crop water need — no irrigation required now."))

    if dry_spell >= 5:
        alerts.append(Alert(type="dryspell", severity="critical",
                            message=f"Dry spell of {dry_spell} rainless days forecast. "
                                    f"Irrigate early, mulch to conserve moisture, and delay fertiliser."))
    elif dry_spell >= 3:
        alerts.append(Alert(type="dryspell", severity="warning",
                            message=f"{dry_spell} dry days ahead — monitor soil moisture closely."))

    if req.growth_stage in ("vegetative", "flowering") and dry_spell < 3:
        alerts.append(Alert(type="fertilizer", severity="info",
                            message=f"Good window for top-dressing nitrogen at the {req.growth_stage} stage."))

    advisory_text = (
        f"Crop water need is about {etc_total:.0f} mm over {days} days; "
        f"rain gives ~{effective_rain:.0f} mm. "
        + (f"Irrigate ~{irrigation:.0f} mm. " if irrigation > 0 else "No irrigation needed now. ")
        + (f"Warning: {dry_spell}-day dry spell coming. " if dry_spell >= 3 else "")
    )

    return AdvisoryResponse(
        plot_id=req.plot_id,
        crop=req.crop,
        et0_mm_day=et0,
        crop_water_requirement_mm=etc_total,
        irrigation_recommended_mm=irrigation,
        dry_spell_days=dry_spell,
        alerts=alerts,
        advisory_text=advisory_text,
        language=req.language,
        model_version=MODEL_VERSION,
    )
