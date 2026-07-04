"""API — Component 1: Smart Crop Recommendation Engine.

Two entry points:
  * /v1/recommendations              — caller supplies soil/rainfall (simple).
  * /v1/recommendations/by-location  — caller supplies only the farm lat/lon;
    the engine fetches soil/weather/rainfall/groundwater itself. This is the
    real Component 1 pipeline (components/crop_recommendation).
"""
from typing import Optional

from fastapi import APIRouter, Query

from app.models.schemas import RecommendationRequest, RecommendationResponse
from app.services import crop_recommendation
from components.crop_recommendation.engine import recommend_from_location
from components.crop_recommendation.schemas import RecommendationResult, Season

router = APIRouter(prefix="/v1", tags=["1 · Crop Recommendation"])


@router.post("/recommendations", response_model=RecommendationResponse)
async def create_recommendation(req: RecommendationRequest) -> RecommendationResponse:
    """Rank the best crops for a plot given soil, groundwater, rainfall & season."""
    return crop_recommendation.recommend(req)


@router.get("/recommendations/by-location", response_model=RecommendationResult)
async def recommend_by_location(
    lat: float = Query(..., ge=-90, le=90, description="Farm latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Farm longitude"),
    season: Optional[Season] = Query(None, description="Auto-inferred from date if omitted"),
    top_n: int = Query(3, ge=1, le=10),
    groundwater_m: Optional[float] = Query(
        None, ge=0, description="Optional farmer-reported borewell/water-table depth (m)"),
) -> RecommendationResult:
    """Recommend crops from just the farm location. The engine assembles soil,
    weather, rainfall and groundwater features (live where available, agro-zone
    estimate otherwise) and runs the L1–L5 pipeline. An optional farmer-reported
    groundwater depth improves accuracy."""
    return await recommend_from_location(
        lat, lon, season=season, top_n=top_n, groundwater_m=groundwater_m)
