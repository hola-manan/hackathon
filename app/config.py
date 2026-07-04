"""Central configuration for the Kisan Alert service.

Everything is env-driven so the same code runs in local demo mode (no external
keys -> deterministic stubs) and in a real deployment (keys present -> live
Bhashini / WhatsApp / Claude calls). Nothing here fails hard if a key is
missing; components degrade gracefully to their stub path.
"""
from __future__ import annotations

import os


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class Settings:
    # ----- WhatsApp Business Cloud API (Meta) -----
    # Display number for the Kisan Alert helpline.
    WHATSAPP_PHONE_NUMBER: str = _get("WHATSAPP_PHONE_NUMBER", "9461330316")
    # phone_number_id + token come from the Meta app; blank in demo mode.
    WHATSAPP_PHONE_NUMBER_ID: str = _get("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_TOKEN: str = _get("WHATSAPP_TOKEN", "")
    WHATSAPP_VERIFY_TOKEN: str = _get("WHATSAPP_VERIFY_TOKEN", "kisan-alert-verify")
    WHATSAPP_API_BASE: str = _get("WHATSAPP_API_BASE", "https://graph.facebook.com/v21.0")

    # ----- Bhashini (ULCA / Dhruva) language stack -----
    BHASHINI_USER_ID: str = _get("BHASHINI_USER_ID", "")
    BHASHINI_API_KEY: str = _get("BHASHINI_API_KEY", "")          # ULCA api key
    BHASHINI_INFERENCE_KEY: str = _get("BHASHINI_INFERENCE_KEY", "")  # Dhruva auth
    BHASHINI_PIPELINE_ID: str = _get(
        "BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd"  # MeitY default ASR+NMT+TTS pipeline
    )
    BHASHINI_CONFIG_URL: str = _get(
        "BHASHINI_CONFIG_URL",
        "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline",
    )

    # ----- Sarvam AI (alternative Indic language stack) -----
    SARVAM_API_KEY: str = _get("SARVAM_API_KEY", "")
    SARVAM_BASE_URL: str = _get("SARVAM_BASE_URL", "https://api.sarvam.ai")
    SARVAM_STT_MODEL: str = _get("SARVAM_STT_MODEL", "saarika:v2.5")
    SARVAM_TRANSLATE_MODEL: str = _get("SARVAM_TRANSLATE_MODEL", "mayura:v1")
    SARVAM_TTS_MODEL: str = _get("SARVAM_TTS_MODEL", "bulbul:v2")
    SARVAM_TTS_SPEAKER: str = _get("SARVAM_TTS_SPEAKER", "anushka")

    # Which Indic language provider to use: "sarvam" | "bhashini" | "auto".
    # "auto" prefers Sarvam if its key is set, else Bhashini, else demo stub.
    LANGUAGE_PROVIDER: str = _get("LANGUAGE_PROVIDER", "auto")

    # ----- Claude (advisory narration + vision diagnosis) -----
    ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = _get("CLAUDE_MODEL", "claude-sonnet-5")

    # ----- App -----
    DEFAULT_LANGUAGE: str = _get("DEFAULT_LANGUAGE", "te")  # Telugu (RSK / Andhra Pradesh)
    SUPPORTED_LANGUAGES = ["te", "hi", "kn", "ta", "en"]

    @property
    def bhashini_live(self) -> bool:
        # The ULCA flow needs only User ID + ULCA API key; the per-request
        # inference key is returned by the getModelsPipeline config call.
        return bool(self.BHASHINI_USER_ID and self.BHASHINI_API_KEY)

    @property
    def sarvam_live(self) -> bool:
        return bool(self.SARVAM_API_KEY)

    @property
    def resolved_language_provider(self) -> str:
        """Which provider is actually active given the configured keys."""
        choice = self.LANGUAGE_PROVIDER.lower()
        if choice == "sarvam":
            return "sarvam"
        if choice == "bhashini":
            return "bhashini"
        # auto
        if self.sarvam_live:
            return "sarvam"
        if self.bhashini_live:
            return "bhashini"
        return "stub"

    @property
    def whatsapp_live(self) -> bool:
        return bool(self.WHATSAPP_PHONE_NUMBER_ID and self.WHATSAPP_TOKEN)

    @property
    def claude_live(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY)


settings = Settings()
