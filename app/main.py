"""Kisan Alert — FastAPI application entrypoint.

Wires the three component APIs, the WhatsApp channel/webhook, and a health
endpoint that reports which integrations are live vs running in demo stub mode.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api import advisories, diagnosis, recommendations, webhook
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Kisan Alert — Smart Water, Crop & Advisory System",
    version="0.1.0",
    description=(
        "Voice-and-WhatsApp agricultural intelligence for small & marginal "
        "farmers. Three components: crop recommendation, real-time advisory & "
        "dry-spell alerts, and photo/voice crop-health diagnosis routed to "
        "Rythu Seva Kendras. Indic language via Bhashini. Helpline: "
        f"{settings.WHATSAPP_PHONE_NUMBER}."
    ),
)

app.include_router(recommendations.router)
app.include_router(advisories.router)
app.include_router(diagnosis.router)
app.include_router(webhook.router)


@app.get("/", tags=["meta"])
async def root():
    return {
        "service": "Kisan Alert",
        "whatsapp_helpline": settings.WHATSAPP_PHONE_NUMBER,
        "default_language": settings.DEFAULT_LANGUAGE,
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
async def health():
    return {
        "status": "ok",
        "integrations": {
            "bhashini": "live" if settings.bhashini_live else "demo-stub",
            "whatsapp": "live" if settings.whatsapp_live else "demo-stub",
            "claude": "live" if settings.claude_live else "demo-stub",
        },
        "components": {
            "crop_recommendation": "up",
            "advisory_dryspell": "up",
            "crop_health_diagnosis": "up",
        },
    }
