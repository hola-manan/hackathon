"""Component 3 — Crop Health Diagnosis (photo / voice -> AI -> RSK).

Production path is two-stage: a fine-tuned CNN classifier + Claude vision
grounded (RAG) on ICAR advisories. In demo mode we run a deterministic
"classifier" (hash of the image bytes indexes a real disease knowledge base)
so the endpoint returns a coherent diagnosis, severity, treatment, and — when
confidence is low or severity high — opens an RSK case. The routing logic,
response shape, and RSK hand-off are exactly what the real models feed into.
"""
from __future__ import annotations

import hashlib
import uuid

from app.models.schemas import DiagnosisResponse

MODEL_VERSION = "diagnosis-cnn+vlm-stub-v0.1"

CONF_ROUTE_THRESHOLD = 0.75   # below -> send to a human expert
SEVERITY_ROUTE = {"high"}     # always route high-severity cases

# Realistic disease knowledge base (treatment lines abbreviated from ICAR/state
# agri advisories). severity drives the RSK routing decision.
_DISEASES = [
    {
        "crop": "Rice", "disease": "Bacterial leaf blight", "severity": "high",
        "treatment": [
            "Drain the field and avoid excess nitrogen.",
            "Spray copper oxychloride (25 g / 10 L) at first symptoms.",
            "Use resistant varieties next season (e.g., Improved Samba Mahsuri).",
        ],
    },
    {
        "crop": "Rice", "disease": "Brown spot", "severity": "moderate",
        "treatment": [
            "Correct potassium and zinc deficiency in soil.",
            "Spray mancozeb (2 g / L) if lesions spread.",
        ],
    },
    {
        "crop": "Tomato", "disease": "Early blight", "severity": "moderate",
        "treatment": [
            "Remove and destroy affected lower leaves.",
            "Spray chlorothalonil or mancozeb at 7–10 day intervals.",
            "Mulch to prevent soil splash.",
        ],
    },
    {
        "crop": "Tomato", "disease": "Late blight", "severity": "high",
        "treatment": [
            "Act fast — this spreads in cool, wet weather.",
            "Spray cymoxanil + mancozeb; repeat after rain.",
            "Improve airflow and avoid overhead irrigation.",
        ],
    },
    {
        "crop": "Cotton", "disease": "Leaf curl virus", "severity": "high",
        "treatment": [
            "Control whitefly vectors (yellow sticky traps, neem oil).",
            "Rogue out and destroy infected plants.",
        ],
    },
    {
        "crop": "Maize", "disease": "Common rust", "severity": "low",
        "treatment": [
            "Usually minor; monitor spread.",
            "Spray propiconazole only if it reaches upper leaves.",
        ],
    },
    {
        "crop": "Healthy", "disease": "No disease detected", "severity": "low",
        "treatment": ["Crop looks healthy. Continue current practice and re-check weekly."],
    },
]


def _classify(image_bytes: bytes, symptom_text: str) -> tuple[dict, float]:
    """Deterministic stand-in for the CNN. Confidence derives from byte
    entropy + whether the farmer's voice symptoms corroborate the class."""
    h = hashlib.sha256(image_bytes or symptom_text.encode() or b"seed").digest()
    idx = h[0] % len(_DISEASES)
    disease = _DISEASES[idx]

    # Base confidence from hash; nudge up when voice symptoms match keywords.
    base = 0.55 + (h[1] / 255.0) * 0.4
    text = symptom_text.lower()
    for kw in ("spot", "blight", "curl", "rust", "yellow", "wilt", "rot"):
        if kw in text and kw in disease["disease"].lower():
            base = min(0.98, base + 0.15)
    return disease, round(base, 2)


def diagnose(image_bytes: bytes, symptom_text: str = "", language: str = "te") -> DiagnosisResponse:
    disease, confidence = _classify(image_bytes, symptom_text)

    route = confidence < CONF_ROUTE_THRESHOLD or disease["severity"] in SEVERITY_ROUTE
    case_id = f"RSK-{uuid.uuid4().hex[:8]}" if route else None

    if disease["disease"] == "No disease detected":
        advisory = "Good news — no disease detected in the photo. Keep monitoring your crop."
    else:
        advisory = (
            f"Detected {disease['disease']} on {disease['crop']} "
            f"(confidence {confidence:.0%}, {disease['severity']} severity). "
            f"First step: {disease['treatment'][0]} "
        )
        if route:
            advisory += (f"This has been referred to your nearest Rythu Seva Kendra "
                        f"(case {case_id}) — an expert will follow up.")

    return DiagnosisResponse(
        diagnosis_id=f"DIAG-{uuid.uuid4().hex[:8]}",
        crop=disease["crop"],
        disease=disease["disease"],
        confidence=confidence,
        severity=disease["severity"],
        treatment_steps=disease["treatment"],
        routed_to_rsk=route,
        case_id=case_id,
        advisory_text=advisory,
        language=language,
        model_version=MODEL_VERSION,
    )
