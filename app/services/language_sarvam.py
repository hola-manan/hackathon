"""Indic language service backed by Sarvam AI.

Implements the same three methods as BhashiniService (transcribe / translate /
synthesize) so it is a drop-in provider. Single-key auth (`api-subscription-key`)
and one REST call per task — simpler than Bhashini's two-step ULCA flow.

Endpoint paths and model names differ across Sarvam API revisions, so they are
config constants (see app/config.py) and responses are parsed defensively.
Falls back to deterministic stubs when no key is set.
"""
from __future__ import annotations

import base64
from typing import Optional

import httpx

from app.config import settings

# Reuse the same demo transcripts so stub behaviour matches across providers.
from app.services.language_bhashini import _STUB_TRANSCRIPTS

# Sarvam expects BCP-47 codes with an Indian region.
_LANG_CODE = {
    "te": "te-IN", "hi": "hi-IN", "en": "en-IN",
    "ta": "ta-IN", "kn": "kn-IN", "ml": "ml-IN", "mr": "mr-IN",
    "bn": "bn-IN", "gu": "gu-IN", "pa": "pa-IN", "od": "od-IN",
}


def _code(lang: str) -> str:
    return _LANG_CODE.get(lang, f"{lang}-IN")


class SarvamService:
    def __init__(self) -> None:
        self.live = settings.sarvam_live
        self.base = settings.SARVAM_BASE_URL.rstrip("/")
        self._headers = {"api-subscription-key": settings.SARVAM_API_KEY}

    # ------------------------------------------------------------------ #
    async def transcribe(self, audio_b64: str, source_lang: str) -> str:
        if not self.live:
            return _STUB_TRANSCRIPTS.get(source_lang, _STUB_TRANSCRIPTS["en"])
        raw = base64.b64decode(audio_b64)
        files = {"file": ("audio.wav", raw, "audio/wav")}
        data = {"model": settings.SARVAM_STT_MODEL, "language_code": _code(source_lang)}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/speech-to-text",
                                  headers=self._headers, data=data, files=files)
            r.raise_for_status()
            body = r.json()
        return body.get("transcript") or body.get("text") or ""

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if source_lang == target_lang or not text:
            return text
        if not self.live:
            return f"[{source_lang}->{target_lang}] {text}"
        payload = {
            "input": text,
            "source_language_code": _code(source_lang),
            "target_language_code": _code(target_lang),
            "model": settings.SARVAM_TRANSLATE_MODEL,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/translate",
                                  headers=self._headers, json=payload)
            r.raise_for_status()
            body = r.json()
        return body.get("translated_text") or text

    async def synthesize(self, text: str, target_lang: str) -> Optional[str]:
        if not self.live or not text:
            return None
        payload = {
            "inputs": [text],
            "target_language_code": _code(target_lang),
            "speaker": settings.SARVAM_TTS_SPEAKER,
            "model": settings.SARVAM_TTS_MODEL,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/text-to-speech",
                                  headers=self._headers, json=payload)
            r.raise_for_status()
            body = r.json()
        audios = body.get("audios") or []
        if not audios:
            return None
        first = audios[0]
        # Some revisions return a list of base64 strings, others list of dicts.
        return first if isinstance(first, str) else first.get("audioContent")
