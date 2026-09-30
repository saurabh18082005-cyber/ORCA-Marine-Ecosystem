# ORCA Live Deployment

## Architecture

Browser (React/Vite) -> FastAPI -> Coordinator -> selected specialist agents -> live providers -> evidence/aggregation -> output + map.

The frontend does not fall back to demo/mock analysis. If a provider is unavailable, ORCA reports the unavailable source instead of fabricating a scientific value.

## Required backend environment variables

Copy `.env.example` to `.env` for local development and fill only the credentials you actually have.

- Bhashini: `BHASHINI_INFERENCE_API_KEY`, `BHASHINI_USER_ID`, `BHASHINI_ULCA_API_KEY`, optional `BHASHINI_PIPELINE_ID`
- Copernicus Marine: `COPERNICUSMARINE_SERVICE_USERNAME`, `COPERNICUSMARINE_SERVICE_PASSWORD`
- Mapbox: `MAPBOX_ACCESS_TOKEN` (optional for the current Leaflet/OpenStreetMap map)
- Protected Planet: `WDPA_API_TOKEN`

Public/no-key sources are configured in `.env.example`: Open-Meteo, Open-Meteo Marine, INCOIS ERDDAP/PFZ, NASA GIBS and OpenStreetMap/Nominatim.

Government `data.gov.in` and IMD credentials are intentionally not required in this version.

## Local backend

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Health: `/api/v1/health`

Query: `POST /api/v1/query`

Location lookup: `GET /api/v1/geocode?q=...`

## Local frontend

```bash
cd frontend
npm ci
npm run dev
```

For deployment, set `VITE_API_BASE_URL` to the public FastAPI URL at build time.

## Render

`render.yaml` contains one FastAPI web service and one static frontend service. Add the private credentials in Render's environment settings; never commit real credentials.

## Mobile

The frontend uses responsive layouts and browser GPS when available. GPS requires HTTPS (or localhost).
