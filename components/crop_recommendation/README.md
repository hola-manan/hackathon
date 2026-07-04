# Component 1 — Smart Crop Recommendation Engine

Self-contained package. **Input: a farm location (lat/lon).** Output: a ranked,
explained crop recommendation with expected yield, water-risk and margin.

Implements the L1–L5 pipeline from `docs/component1-data-model-flow.md`.

## Use it

```python
from components.crop_recommendation.engine import recommend_from_location
res = await recommend_from_location(16.31, 80.44)          # season auto-inferred
print(res.advisory_text)
```

CLI / tests:
```bash
python -m components.crop_recommendation.demo            # 4 sample Indian farms
python -m components.crop_recommendation.demo 16.31 80.44 kharif
python -m components.crop_recommendation.tests          # deterministic unit tests
```

HTTP (via the app):
```bash
uvicorn app.main:app --port 8099
curl "http://127.0.0.1:8099/v1/recommendations/by-location?lat=16.31&lon=80.44"
```

## Pipeline

| Layer | File | Role | Swap-in for production |
|---|---|---|---|
| Feature assembly | `harmonizer.py` + `providers.py` | location → canonical `FeatureVector` | add GEE/SHC/CGWB providers |
| L1 filter | `pipeline.l1_candidates` | EcoCrop/ICAR feasibility (safe, offline) | shapefile agro-zones |
| L2 suitability | `pipeline.l2_suitability` | 0–1 match to crop optimum | XGBoost classifier |
| L3 yield | `pipeline.l3_expected_yield` | expected t/ha | LightGBM on APY/ICRISAT |
| L4 ranking | `pipeline.l4_rank` | water-risk + economic margin | learned reward model |
| L5 confidence | `pipeline.l5_confidence` | provenance + separation | conformal (MAPIE) |
| Narrate | `engine._narrate` | plain-language *why* | Claude + Sarvam TTS |

## Data providers (only operational sources are wired)

| Provider | Source | Key? | Status |
|---|---|---|---|
| `WeatherProvider` | **Open-Meteo** (temp/humidity) + **NASA POWER** (seasonal rainfall climatology) | No | ✅ live |
| `SoilProvider` | agro-zone regional estimate + **farmer Soil Health Card override** | — | ✅ operational |
| `GroundwaterProvider` | **farmer-reported** borewell depth, else regional average | — | ✅ operational |
| `MarketProvider` | **Agmarknet** (data.gov.in) mandi prices, cached out-of-band | sample key (replace for prod) | ✅ live, opportunistic |

**Removed** (were non-operational): SoilGrids live REST (slow ~15s + returns
null at many points — real soil path is the Soil Health Card) and the
GEE/NDVI satellite stub (needs a service account; unused in scoring).

**Why Agmarknet is cached, not live-per-request:** the data.gov.in endpoint is
slow (~15s) and intermittently throttled on the shared sample key, so a live
call would blow the ≤3s reply budget. `refresh_prices.py` (or the app startup
task) warms the cache out-of-band; the request path reads it instantly and
falls back to the KB price table until warm. Use your own free data.gov.in key
for better reliability.

Every provider records whether a value was **live / farmer-supplied vs
regional-estimate**; the engine reports this as `feature_provenance` and lowers
confidence (→ `needs_soil_test`) when soil isn't from the farmer. Passing
`soil_override` / `groundwater_m` (e.g. from the farmer's Soil Health Card)
raises confidence and clears the flag.

## Refreshing prices
```bash
python -m components.crop_recommendation.refresh_prices   # warms mandi-price cache
```

## Design notes
- **Location-first**: the farmer only needs to share their farm pin; no data entry.
- **Honest confidence**: fallback-heavy answers say so and defer to a soil test / RSK.
- **Unit safety**: SoilGrids pH is ÷10; SoilGrids *total* N is deliberately **not**
  mixed with Soil-Health-Card *available* N (see data-flow doc §4).
- **Swap-in seams**: each layer is a pure function; replace with a trained model
  without changing the API or `FeatureVector` contract.
