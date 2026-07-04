"""API stub — Component 3: Crop Health Diagnosis via photo/voice."""
from fastapi import APIRouter, File, Form, UploadFile

from app.models.schemas import DiagnosisResponse
from app.services import diagnosis

router = APIRouter(prefix="/v1", tags=["3 · Crop Health Diagnosis"])


@router.post("/diagnosis", response_model=DiagnosisResponse)
async def create_diagnosis(
    image: UploadFile | None = File(default=None, description="Crop leaf/plant photo"),
    symptom_text: str = Form(default="", description="Voice-described symptoms (transcribed)"),
    language: str = Form(default="te"),
) -> DiagnosisResponse:
    """Diagnose crop disease from a photo (+ optional voice symptoms). Low
    confidence or high severity auto-opens a Rythu Seva Kendra case."""
    image_bytes = await image.read() if image is not None else b""
    return diagnosis.diagnose(image_bytes, symptom_text=symptom_text, language=language)
