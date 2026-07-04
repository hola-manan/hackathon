"""Indic language service backed by Bhashini (ULCA / Dhruva pipelines).

Bhashini is a two-step API:
  1. Ask the ULCA config endpoint (getModelsPipeline) for the compute endpoint
     and inference auth for a given pipeline id + task chain.
  2. POST the payload to that compute endpoint to run ASR / translation / TTS.

If credentials are not configured (demo mode) we fall back to deterministic
stubs so the whole platform still runs end-to-end. The public method
signatures are identical in both modes, so switching to live Bhashini is just
a matter of setting the env vars in app/config.py.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import Optional

import httpx

from app.config import settings

# Task identifiers as used by the ULCA/Dhruva schema.
_ASR = "asr"
_TRANSLATION = "translation"
_TTS = "tts"

# Canned Telugu/Hindi snippets used only in demo (stub) mode so the transcript
# reads naturally in the pipeline logs.
_STUB_TRANSCRIPTS = {
    "te": "నేను ఈ సీజన్‌లో ఏ పంట వేయాలి?",
    "hi": "मुझे इस मौसम में कौन सी फसल लगानी चाहिए?",
    "en": "Which crop should I sow this season?",
}


class BhashiniService:
    def __init__(self) -> None:
        self.live = settings.bhashini_live
        self._pipeline_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # Public API — identical shape in live and stub mode
    # ------------------------------------------------------------------ #
    async def transcribe(self, audio_b64: str, source_lang: str) -> str:
        """Speech (base64 wav/ogg) -> text in the source language."""
        if not self.live:
            return _STUB_TRANSCRIPTS.get(source_lang, _STUB_TRANSCRIPTS["en"])
        payload = self._task_payload(_ASR, source_lang, audio_b64=audio_b64)
        data = await self._compute(payload, [_ASR], source_lang)
        return data["pipelineResponse"][0]["output"][0]["source"]

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if source_lang == target_lang or not text:
            return text
        if not self.live:
            # Stub: tag the string so the flow is visible without a real model.
            return f"[{source_lang}->{target_lang}] {text}"
        payload = self._task_payload(_TRANSLATION, source_lang, target_lang, text=text)
        data = await self._compute(payload, [_TRANSLATION], source_lang, target_lang)
        return data["pipelineResponse"][0]["output"][0]["target"]

    async def synthesize(self, text: str, target_lang: str) -> Optional[str]:
        """Text -> base64 audio. Returns None in stub mode (no audio produced)."""
        if not self.live:
            return None
        payload = self._task_payload(_TTS, target_lang, text=text)
        data = await self._compute(payload, [_TTS], target_lang)
        return data["pipelineResponse"][0]["audio"][0]["audioContent"]

    # ------------------------------------------------------------------ #
    # Live Bhashini plumbing
    # ------------------------------------------------------------------ #
    async def _pipeline_config(self, tasks: list[str], src: str, tgt: Optional[str]) -> dict:
        cache_key = f"{'|'.join(tasks)}:{src}:{tgt}"
        if cache_key in self._pipeline_cache:
            return self._pipeline_cache[cache_key]

        pipeline_tasks = []
        for t in tasks:
            cfg: dict = {"taskType": t, "config": {"language": {"sourceLanguage": src}}}
            if t == _TRANSLATION and tgt:
                cfg["config"]["language"]["targetLanguage"] = tgt
            pipeline_tasks.append(cfg)

        body = {
            "pipelineTasks": pipeline_tasks,
            "pipelineRequestConfig": {"pipelineId": settings.BHASHINI_PIPELINE_ID},
        }
        headers = {
            "userID": settings.BHASHINI_USER_ID,
            "ulcaApiKey": settings.BHASHINI_API_KEY,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(settings.BHASHINI_CONFIG_URL, json=body, headers=headers)
            r.raise_for_status()
            cfg = r.json()
        self._pipeline_cache[cache_key] = cfg
        return cfg

    async def _compute(self, payload_inputs: dict, tasks: list[str],
                       src: str, tgt: Optional[str] = None) -> dict:
        cfg = await self._pipeline_config(tasks, src, tgt)
        endpoint = cfg["pipelineInferenceAPIEndPoint"]
        callback = endpoint["callbackUrl"]
        auth = endpoint["inferenceApiKey"]
        headers = {auth["name"]: auth["value"]}

        # Stitch the service ids returned by config into each task config.
        pipeline_tasks = []
        for task_cfg, resolved in zip(payload_inputs["pipelineTasks"],
                                      cfg["pipelineResponseConfig"]):
            task_cfg["config"]["serviceId"] = resolved["config"][0]["serviceId"]
            pipeline_tasks.append(task_cfg)

        body = {
            "pipelineTasks": pipeline_tasks,
            "inputData": payload_inputs["inputData"],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(callback, json=body, headers=headers)
            r.raise_for_status()
            return r.json()

    def _task_payload(self, task: str, src: str, tgt: Optional[str] = None,
                      *, text: str = "", audio_b64: str = "") -> dict:
        task_cfg: dict = {"taskType": task, "config": {"language": {"sourceLanguage": src}}}
        if task == _TRANSLATION and tgt:
            task_cfg["config"]["language"]["targetLanguage"] = tgt
        input_data: dict = {}
        if audio_b64:
            input_data["audio"] = [{"audioContent": audio_b64}]
        if text:
            input_data["input"] = [{"source": text}]
        return {"pipelineTasks": [task_cfg], "inputData": input_data}


@lru_cache
def get_language_service() -> BhashiniService:
    return BhashiniService()


# Small helper so callers can create a base64 blob in tests/demos.
def to_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()
