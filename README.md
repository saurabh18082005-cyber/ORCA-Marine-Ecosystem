# ORCA — Marine Ecosystem Reasoning with Collaborative Agents

**SIH26176 · Code Forever · East West Institute Of Technology**

ORCA is a FastAPI + React marine-intelligence platform that coordinates specialist agents for weather, ocean, marine ecosystem, fisheries/PFZ, disaster alerts, geospatial restrictions, and satellite context.

## Current architecture

```text
User (web / phone)
      │
      ▼
React + Vite + Leaflet
      │
      ▼
FastAPI /api/v1/query
      │
      ├── BHASHINI NLP
      │     ├── language detection
      │     └── translation to/from English
      │
      ├── Weather Agent
      ├── Ocean Agent
      ├── Marine Agent
      ├── Geospatial Agent
      ├── Disaster & Alerts Agent
      ├── Satellite Agent
      └── Fisheries / PFZ Agent
      │
      ▼
Evidence + cross-agent synthesis
      │
      ▼
Risk / recommendation / evidence / GeoJSON / satellite layers
```

## Integrations

### Multilingual NLP
BHASHINI is used when configured for text-language detection and NMT. The backend keeps a local Unicode detector and localized templates as a fallback. BHASHINI credentials are **backend-only** and must never be placed in Vite frontend environment variables.

### Ocean and satellite
- Copernicus Marine Toolbox for programmatic ocean data access.
- INCOIS integration uses the public Oceansat-2 OCM ERDDAP dataset and the official PFZ bulletin/WebGIS; these endpoints do not require an INCOIS API key.
- NASA GIBS map-ready Earth-observation imagery metadata.
- Optional Sentinel Hub WMS integration.

Copernicus Marine currently documents its official Python Toolbox as the programmatic access path and supports authenticated `open_dataset` access. Credentials can be supplied with `COPERNICUSMARINE_SERVICE_USERNAME` and `COPERNICUSMARINE_SERVICE_PASSWORD`.

### Weather and hazards
- Open-Meteo weather/marine sources remain keyless development/backup sources.
- Optional `IMD_ALERTS_URL` adapter is available for an approved IMD/data.gov.in endpoint.

### Geospatial
The geospatial agent uses ORCA's reference layers for:
- Marine Protected Areas
- International maritime boundary proximity
- Ports
- PFZ/hazard map layers

### Fisheries / PFZ
INCOIS Oceansat-2 OCM chlorophyll is read from the public ERDDAP dataset `incois_oceansat2_datasets`. PFZ uses the official public bulletin/WebGIS endpoints. If PFZ coordinates are not machine-readable from the current bulletin response, ORCA reports them as unavailable rather than inventing a zone.

## Local setup

### Backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate

python -m pip install -r backend/requirements.txt

uvicorn backend.main:app --reload --port 8000
```

Open:
- `http://localhost:8000/docs`
- `http://localhost:8000/api/v1/health`

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Set:

```env
VITE_API_BASE_URL=http://localhost:8000
```

The frontend is responsive and includes browser GPS support plus a PWA manifest/service worker, so the deployed web app can be opened from a phone and installed where supported.

## Environment variables

Copy `.env.example` to `.env` for local backend development.

Important production settings:

```env
ORCA_ALLOW_SIMULATION=false
CORS_ORIGINS=https://your-frontend.example
BHASHINI_INFERENCE_API_KEY=...
BHASHINI_USER_ID=...
BHASHINI_ULCA_API_KEY=...
COPERNICUSMARINE_SERVICE_USERNAME=...
COPERNICUSMARINE_SERVICE_PASSWORD=...
INCOIS_PFZ_BULLETIN_URL=...
IMD_ALERTS_URL=...
```

Do not commit `.env`.

## Deployment

`render.yaml` contains a two-service deployment shape:
- `orca-backend`: FastAPI/uvicorn
- `orca-frontend`: Vite static site

The backend also has a `Dockerfile`.

For Vercel/Netlify, deploy `frontend/` as the project root and set `VITE_API_BASE_URL` to the public FastAPI URL.

## Simulation policy

For local demos, `ORCA_ALLOW_SIMULATION=true` preserves deterministic fallback values if an external source is unavailable.

For a real deployment, use:

```env
ORCA_ALLOW_SIMULATION=false
```

Then missing official data is surfaced as unavailable rather than silently presented as an observation.

## Tests

```bash
python -m pytest backend/tests -q
```

The upgraded repository currently passes the existing **14 backend tests**.

## Important source-access note

Some requested providers do not expose one stable public REST endpoint for every product. ORCA therefore uses provider-specific adapters:
- Copernicus Marine Toolbox for programmatic ocean data.
- Configurable INCOIS bulletin/WMS access for PFZ.
- Configurable IMD/data.gov.in alert endpoint.
- NASA GIBS imagery metadata.

Only credentials/endpoints actually available to the team should be enabled in production.
