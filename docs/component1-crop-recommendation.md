# Component 1 — Smart Crop Recommendation Engine

**Deep-dive: data → datasets → models → integration.**

This document works from first principles: what we must know to recommend a
crop, how to get that data for an Indian small-farmer plot, which datasets and
models exist today, and exactly how to build it into the Kisan Alert codebase.

---

## 0. Reframe the problem (this is the most important step)

"Crop recommendation" is usually built as a single classifier: `soil + climate
→ one crop`. That is the *wrong* target for real farmer value. Two problems:

1. It answers *"what can grow here?"* when the farmer needs *"what should I
   grow to earn the most, at acceptable water-risk, given my constraints?"*
2. It ignores **groundwater, water availability, market price and rotation** —
   exactly the data the challenge statement says farmers lack.

So we frame it as **suitability filter → outcome ranking**, a two-stage
pipeline, not one classifier:

```
candidates → agronomic suitability → ML suitability score → outcome ranking → explanation
 (season +   (EcoCrop/ICAR rule      (XGBoost prob. crop   (yield × price −    (Claude, in
  agro-zone)  ranges, safe filter)    thrives)             cost, water-risk)   Telugu)
```

The "smart" differentiator vs every hackathon crop-classifier: we rank by
**expected profit and water-risk**, groundwater-aware, with a plain-language
*why*. That directly attacks "financial loss and wasted resources."

---

## 1. What data do we need to predict a crop?

Grouped by role in the decision. Each row is a feature family.

| Family | Features | Why it matters |
|---|---|---|
| **Soil chemistry** | N, P, K, pH, organic carbon, EC, S + micros (Zn, Fe, B) | Core suitability; drives fertiliser need |
| **Soil physical** | texture (sand/silt/clay), CEC, bulk density, water-holding capacity | Water retention, root suitability |
| **Climate (season)** | tmin/tmax/mean, humidity, seasonal rainfall, growing-degree-days, agro-climatic zone | Which crops physiologically fit |
| **Weather (forward)** | seasonal rainfall outlook, onset/withdrawal of monsoon | Rainfed risk this season |
| **Remote sensing** | NDVI/EVI history, NDWI/NDMI (moisture), land-surface temp, cropland mask | What *actually* grew well on this land before — ground truth of productivity |
| **Hydrology** | groundwater depth & trend, canal/irrigation availability, rainfed vs irrigated | The water-risk axis — central to this use case |
| **Economics** | mandi price trend, MSP, input cost, demand | Turns "suitable" into "profitable" |
| **Farmer context** | land size, previous crop (rotation), labour, risk appetite | Personalisation & agronomic rotation rules |
| **Temporal** | season (Kharif/Rabi/Zaid), sowing window | Gates the candidate set |

**Minimum viable feature set** (what the Kaggle-style baseline uses): `N, P, K,
pH, temperature, humidity, rainfall`. Good enough to bootstrap; **not** enough
to be "smart" — the water-risk and economic families are what add real value.

---

## 2. How to get each data source (India-specific)

| Source | Access method | Notes / caveats |
|---|---|---|
| **Soil Health Card** (N,P,K,pH,OC,EC,micros) | `soilhealth.dac.gov.in` (v3 portal); bulk & district aggregates on `data.gov.in` | No clean per-farmer public REST API — realistically ingest bulk SHC + district aggregates; let farmer confirm/override via WhatsApp. Primary soil source for India. |
| **SoilGrids** (ISRIC, 250 m global) | GEE community asset `projects/soilgrids-isric/*`; REST `rest.isric.org/soilgrids/v2.0` (⚠ currently paused/beta) | **Cold-start / gap-fill** when no SHC exists for the plot. Use the GEE copy for reliability. |
| **Sentinel-2 NDVI/NDWI** | Google Earth Engine `COPERNICUS/S2_SR_HARMONIZED` | 10 m, 5-day revisit; compute NDVI time-series for the plot polygon. |
| **Soil moisture** | GEE `NASA/SMAP/*` (or Sentinel-1 derived) | 9 km SMAP; feeds water-risk + advisory component. |
| **Rainfall** | GEE `UCSB-CHG/CHIRPS/DAILY`; IMD; Open-Meteo (free forecast) | CHIRPS historical + IMD/Open-Meteo forecast for the season outlook. |
| **Agro-climatic zone** | ICAR 15-zone / NARP zonation (static lookup table) | Cheap, powerful categorical feature. |
| **Groundwater depth** | CGWB / India-WRIS (`indiawris.gov.in`) well data | The water-risk backbone; also used by Component 2. |
| **Mandi prices** | Agmarknet / e-NAM (`data.gov.in` daily price API) | For the economic ranking layer. |
| **District yield history** | ICRISAT VDSA / `data.gov.in` Area-Production-Yield (APY) | Trains the expected-yield model (see §4). |

**Practical acquisition pattern:** resolve `plot_id → lat/lon (or polygon) →
geo-cell`. For that cell, fetch-and-cache each feature (soil from SHC/SoilGrids,
NDVI/moisture/rainfall from GEE, groundwater from CGWB, prices from Agmarknet).
Cache in PostGIS/BigQuery so a recommendation is a fast lookup, not a live
multi-API fan-out.

---

## 3. Datasets available today (for training & rules)

| Dataset | Use | Link |
|---|---|---|
| **Kaggle Crop Recommendation** (2,200 rows, 22 crops, N/P/K/temp/humidity/pH/rainfall) | Bootstrap classifier | kaggle.com/datasets/atharvaingle/crop-recommendation-dataset |
| **FAO EcoCrop** | Rule ranges (temp, rainfall, pH, soil) per crop — the suitability filter | fao.org ecocrop |
| **ICAR crop package-of-practices / suitability** | Region-specific agronomic guardrails & rotation rules | icar.org.in |
| **Soil Health Card bulk / aggregates** | Real Indian soil distributions to re-train & correct Kaggle bias | data.gov.in |
| **District APY (Area-Production-Yield)** | Expected-yield regression per crop×district | data.gov.in / ICRISAT |
| **Sentinel-2 / SMAP / CHIRPS (GEE)** | Live plot features | earthengine.google.com |

**⚠ Critical caveat on the Kaggle dataset:** it is augmented/semi-synthetic and
linearly separable, so models report ~99% accuracy that **will not hold** in the
field. Treat it strictly as a *cold-start bootstrap*. Real accuracy comes from
retraining on SHC + APY + **farmer feedback loops** (did they plant it? what was
the yield?), logged to BigQuery.

---

## 4. Models — what exists, and what we should use

### The landscape (from current literature)
- **Tree ensembles (RandomForest / XGBoost / LightGBM)** on tabular soil+climate — the standard, strong, *interpretable* baseline. Wins on this problem shape.
- **Rule-based suitability (EcoCrop/ICAR ranges)** — no training data, fully explainable, safe guardrail.
- **LSTM / temporal models** on NDVI & weather series — ~86% in 2025 studies; useful once we have multi-season history.
- **Soil-image CNN** (e.g. AgroSense, 2025) — classify soil type / nutrients from a farmer's soil photo; a nice cold-start when no SHC.
- **Uncertainty quantification** (conformal prediction) — return "confidence" so low-certainty cases can ask for a soil test or defer to RSK.
- **LLM (Claude)** — *not* the predictor. Used for explanation, handling free-text constraints ("I only have borewell water twice"), and Telugu narration.

### Recommended layered model (maps to §0 pipeline)

| Layer | Model | Trains on | Output |
|---|---|---|---|
| **L1 Suitability filter** | EcoCrop/ICAR rule ranges | none (knowledge base) | keep/drop each crop + reason |
| **L2 Suitability score** | **XGBoost multiclass** (prob. per crop) | Kaggle → then SHC-augmented | P(crop thrives) |
| **L3 Yield estimate** | **LightGBM regressor per crop** | District APY + soil + weather | expected yield (t/ha) |
| **L4 Outcome ranking** | deterministic scorer | prices (Agmarknet) + cost + water-risk | margin, water-risk-adjusted score |
| **L5 Explanation** | **Claude Sonnet 5** + Sarvam TTS | — | top-3 with *why*, in Telugu |

**Water-risk term (the differentiator):** penalise a crop when its water
requirement (FAO-56 Kc × season length) exceeds available water
(effective rainfall + irrigable groundwater). This is what makes it "smart water
+ crop," not just crop.

Keep L1 as the always-on **safety layer** and offline fallback — even if the ML
model is unavailable, the rule engine still gives a sane, explainable answer.

---

## 5. How to integrate into the Kisan Alert codebase

### Where we are now
`app/services/crop_recommendation.py` already implements **L1 + a simple L4**
(agronomic scoring over N/P/K/pH, groundwater, rainfall, season) behind
`POST /v1/recommendations`. The response shape (`ranked_crops`, `advisory_text`,
`model_version`) is stable and already carries reasons and a water axis.

### Target module layout
```
app/
  features/                         # NEW — feature acquisition, cached
    soil.py         SoilProvider     (SHC → SoilGrids fallback)
    weather.py      WeatherProvider  (IMD / Open-Meteo / CHIRPS)
    satellite.py    EarthEngine      (Sentinel-2 NDVI, SMAP moisture)
    groundwater.py  GroundwaterProvider (CGWB / India-WRIS)
    market.py       MarketProvider   (Agmarknet prices)
    assembler.py    plot_id → cached feature vector
  models/
    crop_reco.pkl                    # trained XGBoost (L2), versioned
    crop_yield_<crop>.pkl            # LightGBM regressors (L3)
  services/
    crop_recommendation.py           # orchestrates L1..L5 (keep rule fallback)
training/
    train_crop_model.py              # Kaggle + SHC → XGBoost; exports .pkl
    train_yield_models.py            # APY → per-crop LightGBM
```

### API evolution (backwards compatible)
`RecommendationRequest` gains an **either/or**: accept raw features (as today,
for testing) **or** just `plot_id` + location and let `features/assembler.py`
hydrate the vector server-side. Response shape unchanged, so WhatsApp/orchestrator
need no edits. `model_version` already lets us A/B rule-only vs XGBoost.

### Phased rollout
- **Phase A (done):** rule scorer, runnable, explainable.
- **Phase B:** train XGBoost on Kaggle, load as L2, blend with L1. Ship `train_crop_model.py`. (fast — a day)
- **Phase C:** wire `features/` providers — SHC/SoilGrids soil + GEE NDVI/moisture + CGWB groundwater; cache to PostGIS. Now recommendations use *real plot data*.
- **Phase D:** add L3 yield + L4 economic ranking (APY + Agmarknet); add uncertainty → defer low-confidence to RSK; start the **feedback loop** (log outcome to BigQuery, retrain).

### Deployability / low-connectivity note
Precompute a **per-village recommendation table** (village × season → top crops)
nightly via the batch pipeline. A WhatsApp/SMS query then returns an instant
lookup even offline, and the live per-plot model refines it when data is
available. This keeps the "runs in a district in weeks" promise intact.

---

## 6. Honest risks & how we handle them

| Risk | Mitigation |
|---|---|
| Kaggle dataset unrealistic (~99% is fake-good) | Bootstrap only; retrain on SHC + APY + farmer feedback |
| Per-farmer SHC has no clean API | Ingest bulk/aggregate SHC; farmer confirms soil via WhatsApp; SoilGrids gap-fill |
| SoilGrids REST API paused | Use GEE-hosted SoilGrids assets |
| GEE auth/quotas at scale | Batch nightly per-village precompute; cache features |
| No soil test for a plot (cold start) | SoilGrids + optional soil-photo CNN + agro-zone priors |
| Model over-confident | Conformal uncertainty → low confidence defers to RSK / requests a soil test |
| Trust / adoption | Always return the *why* (feature reasons) + confidence, in the farmer's language |

---

## 7. TL;DR recommendation

1. **Don't ship a bare classifier.** Build the **suitability-filter → outcome-ranking** pipeline; the profit + water-risk ranking is the value.
2. **Models:** EcoCrop/ICAR rules (safety) + XGBoost suitability + per-crop yield regressor + deterministic economic/water-risk scorer + Claude for Telugu explanation.
3. **Data:** Soil Health Card (primary soil) + SoilGrids (gap-fill) + Sentinel-2/SMAP/CHIRPS via Earth Engine + CGWB groundwater + Agmarknet prices; cache per plot/village.
4. **Bootstrap** on the Kaggle set to demo end-to-end this week, then **retrain on real Indian data + farmer feedback**.
5. **Integrate** behind the existing `POST /v1/recommendations` — add a `features/` layer and a trained model, keep the rule engine as the offline fallback. No API break.

---

## 8. References & links

### Training datasets
- Kaggle Crop Recommendation — https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset
- FAO EcoCrop — https://ecocrop.apps.fao.org/ecocrop/srv/en/home · https://www.fao.org/land-water/land/land-governance/land-resources-planning-toolbox/category/details/en/c/1027491/
- District APY (data.gov.in) — https://www.data.gov.in/catalog/district-wise-season-wise-crop-production-statistics-0 · DES portal https://data.desagri.gov.in/website/crops-apy-report-web
- ICRISAT District Level Database (DLD/VDSA) — http://data.icrisat.org/dld/

### Government / India feature sources
- Soil Health Card — https://www.soilhealth.dac.gov.in/ · open data https://www.data.gov.in/
- CGWB groundwater / India-WRIS — https://indiawris.gov.in/
- Agmarknet — https://agmarknet.gov.in/ · e-NAM — https://www.enam.gov.in/
- ICAR — https://icar.org.in/
- IMD — https://mausam.imd.gov.in/ · Open-Meteo — https://open-meteo.com/

### Soil & satellite layers
- SoilGrids (ISRIC) — https://www.isric.org/explore/soilgrids · REST (beta/paused) https://rest.isric.org/soilgrids/v2.0/docs · GEE assets `projects/soilgrids-isric/*`
- Sentinel-2 SR (GEE) — https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED
- SMAP soil moisture (GEE) — https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL3SMP_E_006
- CHIRPS daily rainfall (GEE) — https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY
- Earth Engine catalog — https://developers.google.com/earth-engine/datasets

### Models / algorithms
- XGBoost — https://xgboost.readthedocs.io/
- LightGBM — https://lightgbm.readthedocs.io/
- RandomForest (scikit-learn) — https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html
- MAPIE (conformal uncertainty) — https://mapie.readthedocs.io/

### Research
- Hybrid DL + rule-based crop recommendation w/ satellite (Nature Sci Rep, 2025) — https://www.nature.com/articles/s41598-025-21506-4
- Incorporating soil information with ML for crop recommendation (Nature Sci Rep, 2025) — https://www.nature.com/articles/s41598-025-88676-z
- ML recommendation of crops under NPK/pH/climate in India (Heliyon, 2024) — https://www.sciencedirect.com/science/article/pii/S2405844024011435 · https://pmc.ncbi.nlm.nih.gov/articles/PMC10844259/
- AgroSense — soil-image DL for crop recommendation (arXiv, 2025) — https://arxiv.org/abs/2509.01344
- Crop recommendation with uncertainty quantification (ScienceDirect, 2025) — https://www.sciencedirect.com/science/article/pii/S2590123025015750

> Caveats: SoilGrids REST API is currently paused (use the GEE copy); per-farmer
> Soil Health Card data has no clean public REST API (use bulk/aggregate SHC +
> farmer confirmation over WhatsApp); the Kaggle dataset is a semi-synthetic
> bootstrap, not field-accurate.
