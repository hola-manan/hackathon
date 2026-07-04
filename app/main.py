"""Kisan Alert — FastAPI application entrypoint.

Wires the three component APIs, the WhatsApp channel/webhook, and a health
endpoint that reports which integrations are live vs running in demo stub mode.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI

from app.api import advisories, diagnosis, recommendations, webhook
from app.config import settings
from components.crop_recommendation.providers import market_provider

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kisan.startup")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm Component 1's mandi-price cache in the background (data.gov.in is
    # slow, so this must never block request handling or startup).
    async def _warm():
        with contextlib.suppress(Exception):
            n = await market_provider.refresh()
            log.info("Agmarknet price cache warmed for %s crops", n)
    task = asyncio.create_task(_warm())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    lifespan=lifespan,
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
            "language_provider": settings.resolved_language_provider,
            "sarvam": "live" if settings.sarvam_live else "demo-stub",
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
