"""WhatsApp Business Cloud API channel adapter.

Helpline number: 9461330316 (configurable via WHATSAPP_PHONE_NUMBER).

In demo mode (no WHATSAPP_TOKEN) outbound sends are logged instead of hitting
Meta, so the full webhook -> orchestrator -> reply loop is exercised locally.
Inbound webhook parsing matches Meta's Cloud API payload schema.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

log = logging.getLogger("kisan.whatsapp")


class WhatsAppClient:
    def __init__(self) -> None:
        self.live = settings.whatsapp_live
        self.number = settings.WHATSAPP_PHONE_NUMBER

    async def send_text(self, to: str, body: str) -> dict:
        if not self.live:
            log.info("[WA demo] -> %s (from %s): %s", to, self.number, body)
            return {"demo": True, "to": to, "from": self.number, "body": body}
        url = f"{settings.WHATSAPP_API_BASE}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()

    async def send_audio_note(self, to: str, audio_b64: Optional[str]) -> dict:
        # Real impl uploads media then sends by id; demo just logs.
        if not audio_b64 or not self.live:
            log.info("[WA demo] -> %s: (voice reply, %s)", to,
                     "audio attached" if audio_b64 else "no audio in demo mode")
            return {"demo": True, "to": to, "audio": bool(audio_b64)}
        return {"note": "audio upload path omitted in scaffold"}


def parse_inbound(payload: dict) -> Optional[dict]:
    """Normalise a Meta webhook body into {from, type, text, audio_id, image_id}."""
    try:
        change = payload["entry"][0]["changes"][0]["value"]
        messages = change.get("messages")
        if not messages:
            return None  # status callback, not a message
        msg = messages[0]
        out = {"from": msg["from"], "type": msg["type"], "text": None,
               "audio_id": None, "image_id": None}
        if msg["type"] == "text":
            out["text"] = msg["text"]["body"]
        elif msg["type"] == "audio":
            out["audio_id"] = msg["audio"]["id"]
        elif msg["type"] == "image":
            out["image_id"] = msg["image"]["id"]
            out["text"] = msg["image"].get("caption")
        return out
    except (KeyError, IndexError):
        return None


whatsapp = WhatsAppClient()
