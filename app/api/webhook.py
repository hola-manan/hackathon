"""WhatsApp webhook — the farmer-facing entry point (helpline 9461330316).

GET  /v1/webhooks/whatsapp  -> Meta verification handshake.
POST /v1/webhooks/whatsapp  -> inbound message -> orchestrator -> reply.

A convenience POST /v1/simulate/whatsapp lets you drive the full pipeline
(ASR -> intent -> component -> translate -> reply) without a real WhatsApp
message, which is what the demo script uses.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from app.channels.whatsapp import parse_inbound, whatsapp
from app.config import settings
from app.services.orchestrator import handle_message

router = APIRouter(prefix="/v1", tags=["WhatsApp Channel"])


@router.get("/webhooks/whatsapp")
async def verify(
    mode: str = Query(default="", alias="hub.mode"),
    token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge"),
):
    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return PlainTextResponse("verification failed", status_code=403)


@router.post("/webhooks/whatsapp")
async def inbound(request: Request):
    body = await request.json()
    msg = parse_inbound(body)
    if not msg:
        return JSONResponse({"status": "ignored"})

    result = await handle_message(
        text=msg.get("text"),
        source_lang=settings.DEFAULT_LANGUAGE,
        # In a full impl we'd download media by id from Meta here.
        image_bytes=b"real-image" if msg.get("image_id") else None,
    )
    await whatsapp.send_text(msg["from"], result["reply_text"])
    if result["reply_audio_b64"]:
        await whatsapp.send_audio_note(msg["from"], result["reply_audio_b64"])
    return JSONResponse({"status": "handled", "intent": result["intent"]})


class SimulateIn(BaseModel):
    from_number: str = "919876543210"
    text: str | None = "నేను ఈ సీజన్‌లో ఏ పంట వేయాలి?"
    language: str = "te"
    has_image: bool = False


@router.post("/simulate/whatsapp")
async def simulate(inp: SimulateIn):
    """Drive the end-to-end farmer pipeline without a live WhatsApp message."""
    result = await handle_message(
        text=inp.text,
        source_lang=inp.language,
        image_bytes=b"demo-leaf-image" if inp.has_image else None,
    )
    sent = await whatsapp.send_text(inp.from_number, result["reply_text"])
    return {
        "helpline": settings.WHATSAPP_PHONE_NUMBER,
        "intent": result["intent"],
        "reply_text": result["reply_text"],
        "voice_reply": bool(result["reply_audio_b64"]),
        "component_payload": result["payload"],
        "whatsapp_send": sent,
    }
