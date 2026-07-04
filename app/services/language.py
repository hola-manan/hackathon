"""Language provider factory.

Returns the configured Indic language service (Sarvam or Bhashini). Both expose
the identical async interface — transcribe / translate / synthesize — so the
orchestrator is provider-agnostic. Selection is driven by LANGUAGE_PROVIDER
(and which keys are present); see Settings.resolved_language_provider.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.services.language_bhashini import BhashiniService
from app.services.language_sarvam import SarvamService


@lru_cache
def get_language_service():
    provider = settings.resolved_language_provider
    if provider == "sarvam":
        return SarvamService()
    # "bhashini" and "stub" both use BhashiniService (it stubs when keyless).
    return BhashiniService()


def active_provider() -> str:
    return settings.resolved_language_provider
