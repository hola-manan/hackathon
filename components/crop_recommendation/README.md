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

## Data providers (live + fallback)

| Provider | Live source (no key) | Fallback |
|---|---|---|
| `WeatherProvider` | **Open-Meteo** forecast + historical archive (real seasonal rainfall) | agro-zone climatology |
| `SoilProvider` | **SoilGrids** REST (ISRIC) | agro-zone soil defaults |
| `GroundwaterProvider` | — (CGWB has no free API) | agro-zone default |
| `MarketProvider` | — (Agmarknet needs data.gov.in key) | KB price table |
| `SatelliteProvider` | — (GEE needs service account) | NDVI omitted |

Every provider records whether a value was **live or fallback**; the engine
reports this as `feature_provenance` and lowers confidence (→ `needs_soil_test`)
when key features are fallback. This keeps the recommendation honest.

## Design notes
- **Location-first**: the farmer only needs to share their farm pin; no data entry.
- **Honest confidence**: fallback-heavy answers say so and defer to a soil test / RSK.
- **Unit safety**: SoilGrids pH is ÷10; SoilGrids *total* N is deliberately **not**
  mixed with Soil-Health-Card *available* N (see data-flow doc §4).
- **Swap-in seams**: each layer is a pure function; replace with a trained model
  without changing the API or `FeatureVector` contract.
