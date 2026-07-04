"""Live smoke-test for the Sarvam language provider.

Run once you have a key:

    export SARVAM_API_KEY=sk_...        # your key
    python -m scripts.test_sarvam

It exercises translation and TTS (and STT if you pass an audio file), printing
real Telugu output. If an endpoint path or model name is off for your API
revision, the HTTP error is printed with the URL so it's a one-line config fix
in app/config.py (SARVAM_* constants).
"""
from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.services.language_sarvam import SarvamService


async def main() -> None:
    if not settings.sarvam_live:
        print("SARVAM_API_KEY not set — export it and re-run.")
        sys.exit(1)

    svc = SarvamService()
    print(f"Base URL      : {settings.SARVAM_BASE_URL}")
    print(f"Models        : stt={settings.SARVAM_STT_MODEL} "
          f"nmt={settings.SARVAM_TRANSLATE_MODEL} tts={settings.SARVAM_TTS_MODEL}\n")

    sample = ("For the kharif season, sorghum is the best fit for your plot "
              "because rainfall is low and groundwater is deep.")

    print("→ translate (en → te)")
    try:
        te = await svc.translate(sample, "en", "te")
        print("  Telugu:", te, "\n")
    except Exception as e:  # noqa: BLE001
        te = None
        print("  translate FAILED:", repr(e), "\n")

    print("→ text-to-speech (te)")
    try:
        audio = await svc.synthesize(te or "మీ పంటకు నీరు పెట్టండి", "te")
        print("  audio base64 length:", len(audio) if audio else 0, "\n")
    except Exception as e:  # noqa: BLE001
        print("  TTS FAILED:", repr(e), "\n")

    if len(sys.argv) > 1:
        path = sys.argv[1]
        import base64
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        print(f"→ speech-to-text ({path}, te)")
        try:
            print("  transcript:", await svc.transcribe(b64, "te"))
        except Exception as e:  # noqa: BLE001
            print("  STT FAILED:", repr(e))
    else:
        print("(pass an audio file path as an argument to also test STT)")


if __name__ == "__main__":
    asyncio.run(main())
