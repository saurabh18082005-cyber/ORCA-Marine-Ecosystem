/**
 * Real ORCA backend integration.
 *
 * Talks to the FastAPI backend built in backend/ (see backend/main.py,
 * backend/api/routes.py) and converts its UnifiedResponse payload into the
 * exact shape the existing UI components already render (see
 * frontend/s../data/uiConstants.js for the reference shape). App.jsx uses this live backend directly; no mock fallback is used.
 */

import { AGENT_STATUS, RISK_LEVELS } from '../data/uiConstants.js'

// If VITE_API_BASE_URL isn't set at build time, fall back to whatever host
// the page itself was loaded from (same protocol + hostname), on the
// backend's default port. A hardcoded 'http://localhost:8000' fallback only
// works when the browser and the backend are the same machine -- on a phone
// loading the frontend from your laptop's LAN IP, "localhost" resolves to
// the phone itself, so every API call would silently fail. Deriving the
// host from window.location means the same build works on a laptop
// (http://localhost:5173 -> http://localhost:8000) and on a phone
// (http://192.168.x.x:5173 -> http://192.168.x.x:8000) without any extra
// configuration. Set VITE_API_BASE_URL explicitly for a real deployment
// where the frontend and backend live on different hosts.
function defaultApiBaseUrl() {
  if (typeof window !== 'undefined' && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`
  }
  return 'http://localhost:8000'
}

export const API_BASE_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
  defaultApiBaseUrl()

function getSessionId() {
  const key = 'orca_session_id'
  let sessionId = sessionStorage.getItem(key)
  if (!sessionId) {
    sessionId = `orca-web-${Math.random().toString(36).slice(2, 10)}`
    sessionStorage.setItem(key, sessionId)
  }
  return sessionId
}

const RISK_LEVEL_MAP = {
  SAFE: RISK_LEVELS.LOW,
  CAUTION: RISK_LEVELS.MODERATE,
  UNSAFE: RISK_LEVELS.HIGH,
  UNAVAILABLE: 'UNAVAILABLE',
}

const RECOMMENDATION_TITLE = {
  SAFE: 'Safe for fishing',
  CAUTION: 'Fishing with caution',
  UNSAFE: 'Avoid fishing',
  UNAVAILABLE: 'Live data unavailable',
}

function agentStatusFromResult(result) {
  if (!result) return AGENT_STATUS.UNAVAILABLE
  if (result.status === 'partial_error' || result.errors?.length) {
    return AGENT_STATUS.UNAVAILABLE
  }
  return AGENT_STATUS.COMPLETED
}

function factorSentiment(severity) {
  if (severity === 'critical' || severity === 'high') return 'negative'
  if (severity === 'moderate') return 'neutral'
  return 'positive'
}

function factorIcon(factorName = '') {
  const name = factorName.toLowerCase()
  if (name.includes('wind')) return '💨'
  if (name.includes('wave')) return '🌊'
  if (name.includes('current')) return '🔄'
  if (name.includes('mpa')) return '🚫'
  if (name.includes('imbl') || name.includes('boundary')) return '🚧'
  if (name.includes('cyclone')) return '🌀'
  return '📊'
}

/**
 * Converts a backend UnifiedResponse (see backend/models/response.py) into
 * the { agents, recommendation, evidence, explanation, map } shape that
 * AgentCards / RecommendationCard / EvidenceCards / ExplanationSection /
 * MapSection already know how to render.
 */
export function mapUnifiedResponseToUI(unified, { lat, lon, locationLabel }) {
  const weather = unified.agent_assessments?.weather_agent
  const ocean = unified.agent_assessments?.ocean_agent
  const marine = unified.agent_assessments?.marine_agent
  const geospatial = unified.agent_assessments?.geospatial_agent
  const disaster = unified.agent_assessments?.disaster_agent
  const satellite = unified.agent_assessments?.satellite_agent
  const fisheries = unified.agent_assessments?.fisheries_agent

  const wData = weather?.data || {}
  const oData = ocean?.data || {}
  const mData = marine?.data || {}
  const gData = geospatial?.data || {}
  const dData = disaster?.data || {}
  const fData = fisheries?.data || {}

  const backendRiskLevel = unified.risk?.level || 'CAUTION'
  const riskLevel = RISK_LEVEL_MAP[backendRiskLevel] || RISK_LEVELS.MODERATE

  const selected = unified.agent_assessments?.coordinator_agent?.selected_agents || []
  const agentEntries = {
    weather_agent: ['weather', 'Weather Agent'],
    ocean_agent: ['ocean', 'Ocean Agent'],
    marine_agent: ['marine', 'Marine Agent'],
    geospatial_agent: ['geospatial', 'Geospatial Agent'],
    disaster_agent: ['disaster', 'Disaster & Alerts Agent'],
    satellite_agent: ['satellite', 'Satellite Agent'],
    fisheries_agent: ['fisheries', 'Fisheries / PFZ Agent'],
  }
  const agents = Object.fromEntries(selected.map((key) => {
    const [uiKey, name] = agentEntries[key] || [key.replace('_agent', ''), key]
    return [uiKey, { name, status: agentStatusFromResult(unified.agent_assessments?.[key]) }]
  }))

  const recommendation = {
    riskLevel,
    title: RECOMMENDATION_TITLE[backendRiskLevel] || 'Analysis complete',
    reason: unified.recommendation,
    confidence: Math.round((unified.risk?.confidence ?? 0.9) * 100),
  }

  const evidence = [
    {
      id: 'wind',
      label: 'Wind',
      value: wData.wind_speed_kmh ?? '—',
      unit: 'km/h',
      description: weather?.assessment?.summary || 'Wind conditions',
      source: weather?.sources?.[0]?.name || 'Open-Meteo',
    },
    {
      id: 'waveHeight',
      label: 'Wave Height',
      value: oData.wave_height_m ?? '—',
      unit: 'm',
      description: ocean?.assessment?.summary || 'Sea state',
      source: ocean?.sources?.[0]?.name || 'Live ocean source',
    },
    {
      id: 'sst',
      label: 'SST',
      value: oData.sea_surface_temperature_c ?? '—',
      unit: '°C',
      description: 'Sea surface temperature',
      source: ocean?.sources?.[0]?.name || 'Live ocean source',
    },
    {
      id: 'chlorophyll',
      label: 'Chlorophyll',
      value: mData.chlorophyll_mg_m3 ?? '—',
      unit: 'mg/m³',
      description: marine?.assessment?.summary || 'Ocean colour reading',
      source: marine?.sources?.[0]?.name || 'Live ocean-colour source',
    },
    {
      id: 'pfz',
      label: 'PFZ',
      value: mData.pfz_detected ? 'Favorable' : 'Not detected',
      unit: '',
      description: mData.mpa_violation
        ? `Inside ${mData.mpa_name || 'a Marine Protected Area'}`
        : 'Potential fishing zone status',
      source: 'INCOIS',
    },
    {
      id: 'warnings',
      label: 'Warnings',
      value: unified.risk?.primary_hazard || 'No major warning',
      unit: '',
      description: mData.mpa_violation
        ? 'Marine Protected Area restriction active'
        : 'Active alerts, if any',
      source: 'IMD / Coast Guard',
    },
    {
      id: 'hazards',
      label: 'Hazard Alerts',
      value: dData.alert_count ?? 0,
      unit: '',
      description: (dData.alerts || []).join(' ') || 'No hazard signal returned',
      source: 'IMD / Open-Meteo',
    },
    {
      id: 'geofence',
      label: 'Geofence',
      value: gData.mpa_violation ? 'Restricted' : 'Clear',
      unit: '',
      description: gData.mpa_name || 'Configured geospatial restrictions',
      source: 'ORCA Geospatial Agent',
    },
    {
      id: 'pfzOfficial',
      label: 'Official PFZ',
      value: fData.pfz_available ? 'Available' : 'Unavailable',
      unit: '',
      description: fData.nearest_pfz ? 'INCOIS PFZ bulletin parsed' : 'No official PFZ bulletin configured',
      source: 'INCOIS',
    },
  ]

  const serverFactors = (unified.risk?.contributing_factors || []).map((f, i) => ({
    id: `factor-${i}`,
    text: f.description,
    sentiment: factorSentiment(f.severity),
    icon: factorIcon(f.factor_name),
  }))

  if (mData.pfz_detected) {
    serverFactors.push({
      id: 'pfz-factor',
      text: 'Potential Fishing Zone detected',
      sentiment: 'positive',
      icon: '📍',
    })
  }

  const explanation = { factors: serverFactors }


  const officialPfz = fData.nearest_pfz
  const map = {
    center: [lat, lon],
    zoom: 10,
    userLocation: { lat, lng: lon, label: `Query Location — ${locationLabel}` },
    pfzZone: officialPfz
      ? { center: [officialPfz.latitude, officialPfz.longitude], label: 'INCOIS Potential Fishing Zone' }
      : null,
    riskZones: [],
    warnings: (dData.alerts || []).map((message, i) => ({ id: `warning-${i}`, lat, lng: lon, message })),
  }

  return { agents, recommendation, evidence, explanation, map }
}

/**
 * Calls the live backend. Network/HTTP failures are surfaced to the UI.
 */
export async function runRealAnalysis({ query, location, datetime, language = 'auto', coordinates = null }) {
  const lat = coordinates?.lat ?? null
  const lon = coordinates?.lon ?? null

  const response = await fetch(`${API_BASE_URL}/api/v1/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: getSessionId(),
      user_query: query,
      latitude: lat,
      longitude: lon,
      language_code: language,
      timestamp: datetime ? new Date(datetime).toISOString() : undefined,
      metadata: { location_name: location },
    }),
  })

  if (!response.ok) {
    throw new Error(`ORCA backend returned ${response.status}`)
  }

  const unified = await response.json()
  const resolved = unified.geojson_layers?.query_location
  return mapUnifiedResponseToUI(unified, { lat: resolved?.latitude ?? lat, lon: resolved?.longitude ?? lon, locationLabel: location || 'Selected location' })
}
