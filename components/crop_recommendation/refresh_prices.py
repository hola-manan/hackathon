"""Out-of-band Agmarknet price refresh for Component 1.

FUNCTIONALITY: warm the MarketProvider price cache by pulling real daily mandi
prices from data.gov.in / Agmarknet. This is intentionally SEPARATE from the
recommendation request path because the data.gov.in endpoint is slow (~15s):
run it on a schedule (nightly cron / Cloud Scheduler) or at server startup, not
per farmer request. In a multi-process deployment the cache should be backed by
Redis/DB; here it warms the in-process cache.

    python -m components.crop_recommendation.refresh_prices
"""
from __future__ import annotations

import asyncio

from . import knowledge as kb
from .providers import market_provider


async def main() -> None:
    crops = list(kb.AGMARKNET_COMMODITY)
    print(f"Refreshing Agmarknet prices for {len(crops)} crops "
          f"(data.gov.in is slow, please wait)…")
    hits = await market_provider.refresh(crops, per_call_timeout=20.0)
    print(f"\nLive prices fetched for {hits}/{len(crops)} crops:\n")
    for crop in crops:
        price, source = market_provider.get_cached_price(crop)
        tag = "LIVE " if source == "agmarknet" else "kb   "
        print(f"  [{tag}] {crop:24s} ₹{price:,.0f}/qtl")


if __name__ == "__main__":
    asyncio.run(main())
