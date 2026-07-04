"""Run Component 1 from a farm location.

    python -m components.crop_recommendation.demo
    python -m components.crop_recommendation.demo 16.31 80.44 kharif
"""
from __future__ import annotations

import asyncio
import sys

from .engine import recommend_from_location
from .schemas import Season

# A few Indian farm locations to show zone-aware behaviour.
SAMPLES = [
    ("Guntur, Andhra Pradesh (Deccan/coastal)", 16.31, 80.44, None),
    ("Ludhiana, Punjab (Indo-Gangetic)", 30.90, 75.85, None),
    ("Jaisalmer, Rajasthan (arid)", 26.91, 70.92, None),
    ("Thrissur, Kerala (west coast)", 10.52, 76.21, None),
]


async def run_one(label, lat, lon, season):
    res = await recommend_from_location(lat, lon, season=season)
    print("\n" + "=" * 72)
    print(f"  {label}   ({lat}, {lon})")
    print("=" * 72)
    print(f"  zone={res.agro_zone}  season={res.season.value}  "
          f"confidence={res.confidence}  soil_test={res.needs_soil_test}")
    print(f"  data: real={res.feature_provenance['real']} "
          f"fallback={res.feature_provenance['fallback']}")
    for i, c in enumerate(res.ranked_crops, 1):
        print(f"  {i}. {c.crop:22s} score={c.score:<5} suit={c.suitability:<5} "
              f"yield={c.expected_yield_t_ha:<5}t/ha water_risk={c.water_risk:<4} "
              f"margin=Rs{c.est_margin_rs_per_ha:,}")
    print("  →", res.advisory_text)


async def main():
    if len(sys.argv) >= 3:
        lat, lon = float(sys.argv[1]), float(sys.argv[2])
        season = Season(sys.argv[3]) if len(sys.argv) > 3 else None
        await run_one(f"custom ({lat},{lon})", lat, lon, season)
        return
    for label, lat, lon, season in SAMPLES:
        await run_one(label, lat, lon, season)


if __name__ == "__main__":
    asyncio.run(main())
