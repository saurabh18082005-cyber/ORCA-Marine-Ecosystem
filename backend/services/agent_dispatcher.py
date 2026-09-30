"""
Asynchronous Multi-Agent Dispatcher for ORCA (SIH26176)

Dispatches concurrent requests to:
- Weather Agent
- Ocean Agent
- Marine Agent

The dispatcher is designed to keep the complete ORCA pipeline working
even when real external data sources are unavailable.

Real agent integrations are attempted where available, with deterministic
fallback/demo values so the frontend always receives a valid response.
"""

import asyncio
import time
import math
import os
from typing import Dict, Any, Optional

from backend.models.agent_schemas import (
    WeatherAgentResponse,
    OceanAgentResponse,
    MarineAgentResponse,
    AgentLocation,
    AgentAssessment,
    AgentSource,
    WeatherData,
    OceanData,
    MarineData,
)

from data.loader import data_loader


# ---------------------------------------------------------------------------
# Real specialist agents
# ---------------------------------------------------------------------------
try:
    from agents.marine_agent import MarineAgent, MarineAgentInput
except Exception:
    MarineAgent = None
    MarineAgentInput = None

try:
    from agents.ocean_agent import OceanAgent, OceanAgentInput
except Exception:
    OceanAgent = None
    OceanAgentInput = None

try:
    from agents.weather_agent import WeatherAgent, WeatherAgentInput
except Exception:
    WeatherAgent = None
    WeatherAgentInput = None

try:
    from agents.geospatial_agent import GeospatialAgent
except Exception:
    GeospatialAgent = None

try:
    from agents.disaster_agent import DisasterAgent
except Exception:
    DisasterAgent = None

try:
    from agents.satellite_agent import SatelliteAgent
except Exception:
    SatelliteAgent = None

try:
    from agents.fisheries_agent import FisheriesAgent
except Exception:
    FisheriesAgent = None


# ---------------------------------------------------------------------------
# Agent Dispatcher
# ---------------------------------------------------------------------------

class AgentDispatcher:
    """
    Coordinates non-blocking parallel dispatch to domain-specialized agents.
    """

    def __init__(self):
        # Reusable real agent instances.
        self._marine_agent = MarineAgent() if MarineAgent else None
        self._ocean_agent = OceanAgent() if OceanAgent else None
        self._weather_agent = WeatherAgent() if WeatherAgent else None
        self._geospatial_agent = GeospatialAgent() if GeospatialAgent else None
        self._disaster_agent = DisasterAgent() if DisasterAgent else None
        self._satellite_agent = SatelliteAgent() if SatelliteAgent else None
        self._fisheries_agent = FisheriesAgent() if FisheriesAgent else None

    # -----------------------------------------------------------------------
    # DISPATCH ALL AGENTS
    # -----------------------------------------------------------------------


    async def dispatch_all(
        self,
        latitude: float,
        longitude: float,
        user_query: str,
        session_id: str,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """Route the query through the Coordinator and run only selected agents."""
        ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        from agents.coordinator_agent.router import AgentRouter
        selected = AgentRouter().route(user_query)

        # If no domain keyword is detected, use a minimal marine-context route
        # rather than silently running every agent.
        if not selected:
            selected = ["weather_agent", "ocean_agent"]

        dispatchers = {
            "weather_agent": lambda: self.dispatch_weather_agent(latitude, longitude, user_query, ts),
            "ocean_agent": lambda: self.dispatch_ocean_agent(latitude, longitude, user_query, ts),
            "marine_agent": lambda: self.dispatch_marine_agent(latitude, longitude, user_query, ts),
            "geospatial_agent": lambda: self.dispatch_geospatial_agent(latitude, longitude, ts),
            "disaster_agent": lambda: self.dispatch_disaster_agent(latitude, longitude, ts),
            "satellite_agent": lambda: self.dispatch_satellite_agent(latitude, longitude, ts),
            "fisheries_agent": lambda: self.dispatch_fisheries_agent(latitude, longitude, ts),
        }

        selected_names = [name for name in selected if name in dispatchers]
        jobs = [dispatchers[name]() for name in selected_names]
        keys = [name.replace("_agent", "") for name in selected_names]
        values = await asyncio.gather(*jobs, return_exceptions=True)

        results = {"coordinator": {
            "agent": "coordinator_agent",
            "status": "success",
            "selected_agents": selected,
            "timestamp": ts,
        }}
        for key, result in zip(keys, values):
            if isinstance(result, Exception):
                results[key] = self._fallback_error_response(
                    f"{key}_agent", latitude, longitude, ts, str(result)
                )
            else:
                results[key] = result
        return results

        # WEATHER AGENT
        # -----------------------------------------------------------------------


    async def dispatch_weather_agent(
        self, lat: float, lon: float, query: str, timestamp: str
    ) -> Dict[str, Any]:
        try:
            port, _ = data_loader.find_nearest_port(lat, lon)
            location_name = port["name"] if port else "Coastal Waters"

            if self._weather_agent is not None:
                try:
                    from agents.weather_agent import WeatherAgentInput
                    output = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._weather_agent.analyze,
                            WeatherAgentInput(
                                lat=lat,
                                lon=lon,
                                location_name=location_name,
                                
                            ),
                        ),
                        timeout=10.0,
                    )
                    if hasattr(output, "to_dict"):
                        payload = output.to_dict()
                        readings = payload.get("readings", [])
                        data = {}
                        for r in readings:
                            name = str(r.get("name", "")).lower().replace(" ", "_")
                            value = r.get("value")
                            if name == "wind_speed":
                                data["wind_speed_kmh"] = value
                            elif name == "temperature":
                                data["temperature_c"] = value
                            elif name == "humidity":
                                data["humidity_pct"] = value
                            elif name == "precipitation":
                                data["precipitation_mm"] = value
                            elif name == "wind_direction":
                                data["wind_direction_deg"] = value
                            elif name == "condition":
                                data["condition"] = value
                        if data:
                                return {
                                    "agent": "weather_agent",
                                    "status": payload.get("status", "success"),
                                "location": {"name": location_name, "latitude": lat, "longitude": lon},
                                "timestamp": payload.get("generated_at", timestamp),
                                "data": data,
                                "assessment": {
                                    "risk_level": "low",
                                    "summary": payload.get("weather_summary", "Weather data retrieved."),
                                },
                                "sources": [{"name": s, "timestamp": payload.get("generated_at", timestamp)} for s in payload.get("sources", ["Open-Meteo"])],
                                "confidence": 0.85 if payload.get("status") == "ok" else 0.60,
                                "errors": payload.get("errors", []),
                            }
                except Exception:
                    pass

            # Deterministic development fallback. Set ORCA_ALLOW_SIMULATION=false
            # in production to surface missing real data instead.
            if os.getenv("ORCA_ALLOW_SIMULATION", "false").lower() != "false":
                wind_speed = round(7.0 + abs(math.cos(lon * 0.3) * 4.0), 1)
                temperature = round(27.0 + math.sin(lat * 0.4) * 2.0, 1)
                return {
                    "agent": "weather_agent",
                    "status": "success",
                    "location": {"name": location_name, "latitude": lat, "longitude": lon},
                    "timestamp": timestamp,
                    "data": {
                        "temperature_c": temperature,
                        "wind_speed_kmh": wind_speed,
                        "humidity_pct": round(72 + abs(math.sin(lat * 0.2) * 10), 1),
                        "precipitation_mm": 0.0,
                        "condition": "Partly Cloudy",
                        "cyclone_warning": False,
                        "lightning_risk": "low",
                    },
                    "assessment": {"risk_level": "low", "summary": "Development fallback weather data."},
                    "sources": [{"name": "ORCA development fallback", "timestamp": timestamp}],
                    "confidence": 0.50,
                    "errors": ["Real weather agent unavailable."],
                }

            return self._fallback_error_response(
                "weather_agent", lat, lon, timestamp, "Real weather data unavailable."
            )
        except Exception as error:
            return self._fallback_error_response("weather_agent", lat, lon, timestamp, str(error))

    # -----------------------------------------------------------------------
    # OCEAN AGENT
    # -----------------------------------------------------------------------

    async def dispatch_ocean_agent(self, lat: float, lon: float, query: str, timestamp: str) -> Dict[str, Any]:
        """Return only live ocean readings from the Ocean Agent."""
        try:
            if not self._ocean_agent or not OceanAgentInput:
                return self._fallback_error_response("ocean_agent", lat, lon, timestamp, "Ocean agent unavailable.")
            output = await asyncio.wait_for(asyncio.to_thread(
                self._ocean_agent.analyze,
                OceanAgentInput(lat=lat, lon=lon, raw_query=query)
            ), timeout=20.0)
            readings = getattr(output, "readings", [])
            data = {}
            sources = []
            for r in readings:
                if r.value is None or r.status in {"mocked", "unavailable", "error"}:
                    continue
                name = str(r.name).lower()
                if name == "wave_height": data["wave_height_m"] = r.value
                elif name == "wave_direction": data["wave_direction_deg"] = r.value
                elif name in {"ocean_current_velocity", "ocean_current"}: data["current_speed_ms"] = r.value
                elif name == "ocean_current_direction": data["current_direction_deg"] = r.value
                elif name == "sea_surface_temperature": data["sea_surface_temperature_c"] = r.value
                elif name == "salinity": data["salinity_psu"] = r.value
                if getattr(r, "source", None): sources.append(r.source)
            if not data:
                return self._fallback_error_response("ocean_agent", lat, lon, timestamp, "No live ocean observations were returned.")
            return {
                "agent": "ocean_agent", "status": "success",
                "location": {"latitude": lat, "longitude": lon}, "timestamp": getattr(output, "generated_at", timestamp),
                "data": data, "assessment": {"risk_level": "unknown", "summary": getattr(output, "ocean_summary", "Live ocean data retrieved.")},
                "sources": [{"name": x, "timestamp": getattr(output, "generated_at", timestamp)} for x in sorted(set(sources))],
                "confidence": 0.90, "errors": getattr(output, "errors", []),
            }
        except Exception as error:
            return self._fallback_error_response("ocean_agent", lat, lon, timestamp, str(error))

    # -----------------------------------------------------------------------
    # MARINE AGENT
    # -----------------------------------------------------------------------

    async def dispatch_marine_agent(self, lat: float, lon: float, query: str, timestamp: str) -> Dict[str, Any]:
        """Return live marine/ecosystem data; never synthesize scientific values."""
        try:
            if not self._marine_agent or not MarineAgentInput:
                return self._fallback_error_response("marine_agent", lat, lon, timestamp, "Marine agent unavailable.")
            output = await asyncio.wait_for(asyncio.to_thread(
                self._marine_agent.analyze,
                MarineAgentInput(lat=lat, lon=lon, raw_query=query)
            ), timeout=30.0)
            readings = getattr(output, "readings", [])
            data = {}
            sources = []
            for r in readings:
                if r.value is None or r.status in {"mocked", "unavailable", "error"}:
                    continue
                name = str(r.name).lower()
                if name == "chlorophyll": data["chlorophyll_mg_m3"] = r.value
                elif name == "sea_surface_temperature": data["sea_surface_temperature_c"] = r.value
                elif name == "salinity": data["salinity_psu"] = r.value
                elif name == "current_speed": data["current_speed_ms"] = r.value
                if getattr(r, "source", None): sources.append(r.source)
            if not data:
                return self._fallback_error_response("marine_agent", lat, lon, timestamp, "No live marine observations were returned.")
            return {
                "agent": "marine_agent", "status": "success",
                "location": {"latitude": lat, "longitude": lon}, "timestamp": getattr(output, "generated_at", timestamp),
                "data": data, "assessment": {"risk_level": "unknown", "summary": getattr(output, "ecosystem_summary", "Live marine data retrieved.")},
                "sources": [{"name": x, "timestamp": getattr(output, "generated_at", timestamp)} for x in sorted(set(sources))],
                "confidence": 0.90 if data else 0.0, "errors": getattr(output, "errors", []),
            }
        except Exception as error:
            return self._fallback_error_response("marine_agent", lat, lon, timestamp, str(error))

    async def dispatch_geospatial_agent(self, lat: float, lon: float, timestamp: str) -> Dict[str, Any]:
        if not self._geospatial_agent:
            return self._fallback_error_response("geospatial_agent", lat, lon, timestamp, "Agent unavailable.")
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._geospatial_agent.analyze, lat, lon), timeout=10.0
            )
        except Exception as exc:
            return self._fallback_error_response("geospatial_agent", lat, lon, timestamp, str(exc))

    async def dispatch_disaster_agent(self, lat: float, lon: float, timestamp: str) -> Dict[str, Any]:
        if not self._disaster_agent:
            return self._fallback_error_response("disaster_agent", lat, lon, timestamp, "Agent unavailable.")
        try:
            # Outer guard on top of the agent's own per-request timeout
            # (10s IMD + 10s Open-Meteo internally): caps the absolute
            # worst case for this one agent regardless of what the agent's
            # own timeout handling does, so a single slow/misbehaving
            # external endpoint can't stall the whole /api/v1/query
            # response past this ceiling.
            return await asyncio.wait_for(
                asyncio.to_thread(self._disaster_agent.analyze, lat, lon), timeout=15.0
            )
        except Exception as exc:
            return self._fallback_error_response("disaster_agent", lat, lon, timestamp, str(exc))

    async def dispatch_satellite_agent(self, lat: float, lon: float, timestamp: str) -> Dict[str, Any]:
        if not self._satellite_agent:
            return self._fallback_error_response("satellite_agent", lat, lon, timestamp, "Agent unavailable.")
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._satellite_agent.analyze, lat, lon), timeout=10.0
            )
        except Exception as exc:
            return self._fallback_error_response("satellite_agent", lat, lon, timestamp, str(exc))

    async def dispatch_fisheries_agent(self, lat: float, lon: float, timestamp: str) -> Dict[str, Any]:
        if not self._fisheries_agent:
            return self._fallback_error_response("fisheries_agent", lat, lon, timestamp, "Agent unavailable.")
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._fisheries_agent.analyze, lat, lon), timeout=15.0
            )
        except Exception as exc:
            return self._fallback_error_response("fisheries_agent", lat, lon, timestamp, str(exc))

    # -----------------------------------------------------------------------
    # FALLBACK ERROR RESPONSE
    # -----------------------------------------------------------------------

    def _fallback_error_response(
        self,
        agent_name: str,
        lat: float,
        lon: float,
        timestamp: str,
        error_msg: str
    ) -> Dict[str, Any]:
        """
        Final safety fallback.

        Even if an individual agent encounters an unexpected error,
        the dispatcher returns a structured result instead of allowing
        the entire ORCA request to fail.
        """

        return {
            "agent": agent_name,
            "status": "partial_error",
            "location": {
                "name": "Location",
                "latitude": lat,
                "longitude": lon
            },
            "timestamp": timestamp,
            "data": {},
            "assessment": {
                "risk_level": "unavailable",
                "summary": f"Agent {agent_name} did not return live data."
            },
            "sources": [
                {
                    "name": "Live data unavailable",
                    "timestamp": timestamp
                }
            ],
            "confidence": 0.0,
            "errors": [error_msg]
        }


# ---------------------------------------------------------------------------
# Global dispatcher instance
# ---------------------------------------------------------------------------

agent_dispatcher = AgentDispatcher()
