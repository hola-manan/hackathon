"""API stub — Component 2: Real-time Advisory & Dry-Spell Alerts."""
from fastapi import APIRouter

from app.models.schemas import AdvisoryRequest, AdvisoryResponse
from app.services import advisory

router = APIRouter(prefix="/v1", tags=["2 · Advisory & Dry-Spell"])


@router.post("/advisories", response_model=AdvisoryResponse)
async def create_advisory(req: AdvisoryRequest) -> AdvisoryResponse:
    """Irrigation/fertiliser guidance + dry-spell alerts from a weather forecast."""
    return advisory.advise(req)
