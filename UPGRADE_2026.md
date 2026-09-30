# ORCA 2026 Upgrade

## Implemented

### NLP / Multilingual
- BHASHINI text language detection using the official Dhruva inference endpoint.
- BHASHINI NMT translation into English before agent processing.
- BHASHINI NMT translation of the final recommendation back to the requested/detected language.
- The ULCA config call is performed dynamically so ORCA obtains the correct translation service ID and inference key for the configured pipeline; no inference secret is committed to the repository.
- Local script detection and localized templates remain as fallbacks.
- Frontend language selector with Auto-detect.
- Backend secrets remain server-side.

### New specialist agents
- Geospatial Agent: MPA + IMBL + nearest-port reasoning.
- Disaster & Alerts Agent: configurable IMD endpoint + Open-Meteo hazard fallback.
- Satellite Agent: NASA GIBS imagery metadata + optional Sentinel Hub WMS.
- Fisheries/PFZ Agent: configurable INCOIS bulletin parser + optional WMS metadata.

### Existing data layer
- Existing Marine Agent keeps Copernicus Marine integration.
- Existing Weather Agent keeps Open-Meteo integration.
- Existing Ocean Agent keeps chlorophyll/IRS-P4 OCM path.
- Dispatcher now executes seven specialist agents concurrently.

### Evidence / reasoning
- Aggregator now incorporates new agent outputs.
- Hazard alerts and geospatial restrictions enter the evidence/risk synthesis.
- Agent confidence is used as an input to the aggregate confidence.
- Satellite and PFZ provenance are exposed in the response.

### Phone / deployment
- Responsive frontend retained and extended.
- Browser GPS button added.
- PWA manifest and service worker added.
- Render blueprint added for backend + frontend.
- Dockerfile added for backend.
- `.env.example` added.
- Production simulation switch added:
  `ORCA_ALLOW_SIMULATION=false`

## Provider choices

The original upgrade list contains alternatives, not requirements to install every provider simultaneously.

ORCA currently chooses:
- BHASHINI for multilingual NLP.
- Copernicus Marine for programmatic ocean data.
- Open-Meteo for keyless weather/marine fallback.
- NASA GIBS for satellite imagery context.
- Leaflet/OpenStreetMap + server-side geospatial layers for mapping.
- Configurable INCOIS PFZ bulletin/WMS and IMD alert adapters.

LangGraph/CrewAI, Claude/GPT, Mapbox/Google Maps, OpenWeather/Windy, and Pinecone/Weaviate/pgvector are therefore not hard dependencies in this upgrade. Adding multiple competing orchestration/LLM/vector providers at once would increase deployment risk without improving the current core pipeline.

## Production data requirements

Before public deployment, configure:
- BHASHINI credentials from the approved account.
- Copernicus Marine credentials.
- An approved INCOIS PFZ bulletin/WMS endpoint.
- An approved IMD/data.gov.in alert endpoint if required.
- The exact satellite layer IDs approved for the demo.
- `CORS_ORIGINS` to the deployed frontend URL.
- `VITE_API_BASE_URL` to the deployed backend URL.

The code deliberately does not invent PFZ, IMD, or satellite numeric observations when the official source is unavailable.

## Verification

Backend:
`python -m pytest backend/tests -q`

Current backend result:
`16 passed`

The frontend dependency installation/build was not completed in this environment because the npm dependency download timed out; run `npm ci && npm run build` in the team's normal development/deployment environment before merging.
