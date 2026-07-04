# Kisan Alert — Smart Water, Crop & Advisory System

Voice-and-WhatsApp agricultural intelligence for small & marginal farmers, in
Indic languages via **Bhashini**. WhatsApp helpline: **9461330316**.

Three components, each exposed as its own API and reachable through one
WhatsApp conversation:

| # | Component | Endpoint | What it does |
|---|-----------|----------|--------------|
| 1 | **Smart Crop Recommendation** | `POST /v1/recommendations` | Ranks best crops for a plot from soil NPK/pH, groundwater depth, seasonal rainfall & season, each with a plain reason. |
| 2 | **Real-time Advisory & Dry-Spell Alerts** | `POST /v1/advisories` | FAO-56 water-balance → irrigation/fertiliser guidance + dry-spell alerts from a weather forecast. |
| 3 | **Crop Health Diagnosis** | `POST /v1/diagnosis` | Photo (+ voice symptoms) → disease, severity & treatment; low-confidence/high-severity cases auto-open a **Rythu Seva Kendra** case. |

The design doc & architecture diagram live alongside this prototype (see the
approved plan / artifact).

## Architecture in one line

```
Farmer (WhatsApp voice/photo/text, 9461330316)
   → Bhashini ASR/Translation/TTS
   → Claude orchestrator (intent routing)
   → [Crop Reco | Advisory & Dry-Spell | Diagnosis]
   → reply in farmer's language  ·  hard cases → Rythu Seva Kendra
```

## Run it (demo mode — no keys needed)

```bash
pip install -r requirements.txt

# End-to-end walkthrough of all 3 components + the WhatsApp pipeline:
python -m scripts.demo

# Or run the API server and open interactive docs:
uvicorn app.main:app --reload --port 8099
#   http://127.0.0.1:8099/docs
#   http://127.0.0.1:8099/health   -> shows which integrations are live vs stub
```

### Try the endpoints

```bash
B=http://127.0.0.1:8099

# 1 · Crop recommendation
curl -s -X POST $B/v1/recommendations -H 'Content-Type: application/json' -d '{
  "season":"kharif","soil":{"n":260,"p":22,"k":190,"ph":6.6},
  "groundwater_depth_m":28,"seasonal_rainfall_mm":520}'

# 2 · Advisory & dry-spell
curl -s -X POST $B/v1/advisories -H 'Content-Type: application/json' -d '{
  "crop":"rice","growth_stage":"vegetative","soil_moisture_pct":28,
  "forecast":[{"day":1,"rain_mm":0,"tmax":37,"tmin":25}]}'

# 3 · Diagnosis (photo + voice symptom)
curl -s -X POST $B/v1/diagnosis -F "image=@leaf.jpg" \
  -F "symptom_text=brown spots on rice leaves" -F "language=te"

# Full WhatsApp pipeline without a real message
curl -s -X POST $B/v1/simulate/whatsapp -H 'Content-Type: application/json' \
  -d '{"text":"నా వరి ఆకులపై మచ్చలు","language":"te","has_image":true}'
```

## Demo mode vs live

Everything runs with **zero external keys** — Bhashini, WhatsApp and Claude
each fall back to a deterministic stub so the whole flow is exercised locally
(translation shows as `[en->te] …` tags, WhatsApp sends are logged). The
component logic (crop scoring, FAO-56 water balance, diagnosis routing) is
real, not mocked.

To go live, copy `.env.example` → `.env` and fill in credentials:

- **Bhashini**: `BHASHINI_USER_ID`, `BHASHINI_API_KEY`, `BHASHINI_INFERENCE_KEY`
  (ULCA/Dhruva). The two-step config→compute call is implemented in
  `app/services/language_bhashini.py`.
- **WhatsApp Cloud API**: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_TOKEN`. Point
  Meta's webhook at `POST /v1/webhooks/whatsapp` (verify token
  `WHATSAPP_VERIFY_TOKEN`).
- **Claude**: `ANTHROPIC_API_KEY` for advisory narration & vision diagnosis.

`GET /health` reports the live/stub status of each.

## Layout

```
app/
  main.py                     FastAPI app + /health
  config.py                   env-driven settings (helpline 9461330316)
  models/schemas.py           request/response models for all 3 components
  api/                        the 3 component API stubs + WhatsApp webhook
    recommendations.py  advisories.py  diagnosis.py  webhook.py
  services/
    crop_recommendation.py    agronomic scoring (→ swap in XGBoost/LightGBM)
    advisory.py               FAO-56 Penman/Hargreaves water balance + dry-spell
    diagnosis.py              CNN + Claude-vision stub + RSK routing
    language_bhashini.py      Bhashini ASR / translation / TTS (live + stub)
    orchestrator.py           intent routing across components
  channels/whatsapp.py        WhatsApp Cloud API adapter (live + demo log)
scripts/demo.py               end-to-end walkthrough
```

Each service is a drop-in seam: replace the demo scoring/classifier with the
production model without changing the API or response shape.
