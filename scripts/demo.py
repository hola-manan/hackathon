"""End-to-end demo driver for Kisan Alert.

Runs each of the three components directly AND through the WhatsApp
orchestrator pipeline, printing the farmer-facing reply each time.

    python -m scripts.demo
"""
from __future__ import annotations

import asyncio
import json

from app.models.schemas import (
    AdvisoryRequest, DayForecast, RecommendationRequest, Season, SoilProfile,
)
from app.services import advisory, crop_recommendation, diagnosis
from app.services.orchestrator import handle_message


def line(title: str) -> None:
    print("\n" + "=" * 68 + f"\n  {title}\n" + "=" * 68)


async def main() -> None:
    # 1 · Crop recommendation
    line("1 · CROP RECOMMENDATION")
    rec = crop_recommendation.recommend(RecommendationRequest(
        season=Season.kharif,
        soil=SoilProfile(n=260, p=22, k=190, ph=6.6, organic_carbon=0.6),
        groundwater_depth_m=28.0, seasonal_rainfall_mm=520.0,
    ))
    for c in rec.ranked_crops:
        print(f"  {c.crop:24s} score={c.score:<5} water={c.water_need:<7} — {c.reason}")
    print("  advisory:", rec.advisory_text)

    # 2 · Advisory & dry-spell
    line("2 · ADVISORY & DRY-SPELL")
    adv = advisory.advise(AdvisoryRequest(
        crop="rice", growth_stage="vegetative", soil_moisture_pct=28.0,
        forecast=[DayForecast(day=i, rain_mm=(12.0 if i == 7 else 0.0),
                              tmax=37 - (i % 3), tmin=25) for i in range(1, 8)],
    ))
    print(f"  ET0={adv.et0_mm_day} mm/day  ETc={adv.crop_water_requirement_mm} mm  "
          f"irrigate={adv.irrigation_recommended_mm} mm  dry_spell={adv.dry_spell_days} days")
    for a in adv.alerts:
        print(f"  [{a.severity:8s}] {a.type}: {a.message}")

    # 3 · Diagnosis (photo + voice symptom)
    line("3 · CROP HEALTH DIAGNOSIS")
    dg = diagnosis.diagnose(b"a-crop-leaf-photo-bytes", symptom_text="brown spots on rice leaves")
    print(f"  {dg.crop} / {dg.disease}  conf={dg.confidence:.0%}  severity={dg.severity}")
    print(f"  routed_to_rsk={dg.routed_to_rsk}  case_id={dg.case_id}")
    print("  advisory:", dg.advisory_text)

    # 4 · Full WhatsApp pipeline (voice text in Telugu -> reply)
    line("4 · WHATSAPP PIPELINE (helpline 9461330316)")
    for text, img in [
        ("నేను ఈ సీజన్‌లో ఏ పంట వేయాలి?", False),
        ("నా వరి ఆకులపై మచ్చలు ఉన్నాయి", True),
        ("పంటకు నీరు ఎప్పుడు పెట్టాలి?", False),
    ]:
        out = await handle_message(text=text, source_lang="te",
                                   image_bytes=b"leaf" if img else None)
        print(f"\n  farmer(te): {text}")
        print(f"  intent    : {out['intent']}")
        print(f"  reply     : {out['reply_text']}")


if __name__ == "__main__":
    asyncio.run(main())
