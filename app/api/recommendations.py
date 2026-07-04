"""API stub — Component 1: Smart Crop Recommendation Engine."""
from fastapi import APIRouter

from app.models.schemas import RecommendationRequest, RecommendationResponse
from app.services import crop_recommendation

router = APIRouter(prefix="/v1", tags=["1 · Crop Recommendation"])


@router.post("/recommendations", response_model=RecommendationResponse)
async def create_recommendation(req: RecommendationRequest) -> RecommendationResponse:
    """Rank the best crops for a plot given soil, groundwater, rainfall & season."""
    return crop_recommendation.recommend(req)
