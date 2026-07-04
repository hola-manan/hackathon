"""Conversation Orchestrator — routes an inbound farmer message to the right
component and returns a localized reply.

Production uses a Claude agent for intent + slot-filling + tool-calls. The demo
uses a lightweight keyword intent router so the whole path runs without keys,
while the seams for ASR/translation/TTS (Bhashini) and per-component calls are
all real.
"""
from __future__ import annotations

import logging

from app.models.schemas import (
    AdvisoryRequest, DayForecast, RecommendationRequest, Season, SoilProfile,
)
from app.services import advisory, crop_recommendation, diagnosis
from app.services.language import get_language_service

log = logging.getLogger("kisan.orchestrator")


async def _safe_transcribe(lang, audio_b64, source_lang) -> str:
    try:
        return await lang.transcribe(audio_b64, source_lang)
    except Exception as e:  # noqa: BLE001
        log.warning("ASR failed (%s); continuing without transcript", e)
        return ""


async def _safe_translate(lang, text, src, tgt) -> str:
    try:
        return await lang.translate(text, src, tgt)
    except Exception as e:  # noqa: BLE001
        log.warning("translation failed (%s); returning source text", e)
        return text  # degrade to untranslated text rather than dropping the reply


async def _safe_synthesize(lang, text, tgt):
    try:
        return await lang.synthesize(text, tgt)
    except Exception as e:  # noqa: BLE001
        log.warning("TTS failed (%s); replying text-only", e)
        return None

# Demo plot baseline (in production this is loaded from PostGIS by plot_id,
# hydrated from Soil Health Card + CGWB + satellite).
_DEMO_PLOT = {
    "soil": SoilProfile(n=260, p=22, k=190, ph=6.6, organic_carbon=0.6),
    "groundwater_depth_m": 28.0,
    "seasonal_rainfall_mm": 520.0,
}

_DEMO_FORECAST = [
    DayForecast(day=1, rain_mm=0.0, tmax=36, tmin=25),
    DayForecast(day=2, rain_mm=0.0, tmax=37, tmin=26),
    DayForecast(day=3, rain_mm=0.0, tmax=38, tmin=26),
    DayForecast(day=4, rain_mm=0.0, tmax=37, tmin=25),
    DayForecast(day=5, rain_mm=0.0, tmax=36, tmin=24),
    DayForecast(day=6, rain_mm=1.0, tmax=35, tmin=24),
    DayForecast(day=7, rain_mm=12.0, tmax=32, tmin=23),
]

_REC_KW = ("crop", "grow", "sow", "plant", "పంట", "फसल", "recommend")
_DIAG_KW = ("disease", "sick", "spot", "blight", "pest", "leaf", "రోగం", "रोग")
_ADV_KW = ("water", "irrigat", "rain", "dry", "fertil", "నీరు", "पानी", "सिंचाई")


def detect_intent(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in _DIAG_KW):
        return "diagnosis"
    if any(k in t for k in _ADV_KW):
        return "advisory"
    if any(k in t for k in _REC_KW):
        return "recommendation"
    return "recommendation"  # sensible default for a farming helpline


async def handle_message(
    *, text: str | None, source_lang: str,
    audio_b64: str | None = None, image_bytes: bytes | None = None,
) -> dict:
    """Returns {intent, reply_text, reply_audio_b64, payload}."""
    lang = get_language_service()

    # 1. Voice -> text (Bhashini ASR)
    if audio_b64 and not text:
        text = await _safe_transcribe(lang, audio_b64, source_lang)

    # 2. Image present -> diagnosis regardless of text
    if image_bytes:
        intent = "diagnosis"
    else:
        # Work in English internally, then reply in the farmer's language.
        english = await _safe_translate(lang, text or "", source_lang, "en")
        intent = detect_intent(english if source_lang != "en" else (text or ""))

    if intent == "diagnosis":
        result = diagnosis.diagnose(image_bytes or b"", symptom_text=text or "", language=source_lang)
        english_reply = result.advisory_text
        payload = result.model_dump()
    elif intent == "advisory":
        req = AdvisoryRequest(crop="rice", growth_stage="vegetative",
                              soil_moisture_pct=28.0, forecast=_DEMO_FORECAST, language=source_lang)
        result = advisory.advise(req)
        english_reply = result.advisory_text + " " + " ".join(a.message for a in result.alerts)
        payload = result.model_dump()
    else:
        req = RecommendationRequest(season=Season.kharif, soil=_DEMO_PLOT["soil"],
                                    groundwater_depth_m=_DEMO_PLOT["groundwater_depth_m"],
                                    seasonal_rainfall_mm=_DEMO_PLOT["seasonal_rainfall_mm"],
                                    language=source_lang)
        result = crop_recommendation.recommend(req)
        english_reply = result.advisory_text
        payload = result.model_dump()

    # 3. English -> farmer language (NMT) then TTS, both degrade gracefully.
    reply_text = await _safe_translate(lang, english_reply, "en", source_lang)
    reply_audio = await _safe_synthesize(lang, reply_text, source_lang)

    return {
        "intent": intent,
        "reply_text": reply_text,
        "reply_audio_b64": reply_audio,
        "payload": payload,
    }
