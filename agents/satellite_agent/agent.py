from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Dict


class SatelliteAgent:
    """
    Satellite/Earth-observation metadata agent.

    GIBS and Sentinel Hub layer URLs are configurable so the deployment can
    select the exact operational product without hard-coding an unverified
    product identifier. This agent exposes map-ready imagery metadata rather
    than inventing a numeric observation.
    """

    def analyze(self, lat: float, lon: float) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        gibs_base = os.getenv(
            "NASA_GIBS_BASE_URL",
            "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best",
        )
        gibs_layer = os.getenv(
            "NASA_GIBS_LAYER",
            "MODIS_Aqua_CorrectedReflectance_TrueColor",
        )
        sentinel_url = os.getenv("SENTINEL_HUB_WMS_URL")

        layers = [{
            "provider": "NASA GIBS",
            "layer": gibs_layer,
            "base_url": gibs_base,
            "center": {"lat": lat, "lon": lon},
        }]
        if sentinel_url:
            layers.append({
                "provider": "Sentinel Hub",
                "wms_url": sentinel_url,
                "center": {"lat": lat, "lon": lon},
            })

        return {
            "agent": "satellite_agent",
            "status": "success",
            "location": {"latitude": lat, "longitude": lon},
            "timestamp": now,
            "data": {
                "earth_observation_layers": layers,
                "imagery_available": True,
                "note": "Imagery layer metadata is available; numeric ocean observations remain sourced from dedicated ocean datasets.",
            },
            "assessment": {
                "risk_level": "low",
                "summary": "Satellite imagery layers are available for contextual Earth-observation analysis.",
            },
            "sources": [{"name": "NASA GIBS", "timestamp": now}],
            "confidence": 0.95,
            "errors": [],
        }
