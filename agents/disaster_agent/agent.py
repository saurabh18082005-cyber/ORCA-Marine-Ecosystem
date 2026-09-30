from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Dict
import requests


class DisasterAgent:
    """
    Hazard intelligence agent.

    Open-Meteo is used as a keyless fallback for thunderstorm/wind conditions.
    An IMD response can be injected through IMD_ALERTS_URL when an approved
    IMD/data.gov.in endpoint is configured for the deployment.
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def analyze(self, lat: float, lon: float) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        alerts = []
        errors = []
        sources = []

        imd_url = os.getenv("IMD_ALERTS_URL")
        if imd_url:
            try:
                r = requests.get(
                    imd_url,
                    params={"latitude": lat, "longitude": lon},
                    timeout=self.timeout,
                )
                r.raise_for_status()
                data = r.json()
                sources.append("India Meteorological Department")
                alerts.extend(self._extract_alerts(data))
            except Exception as exc:
                errors.append(f"IMD alert source failed: {exc}")

        try:
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "wind_speed_10m,weather_code",
                    "hourly": "weather_code,wind_speed_10m",
                    "forecast_days": 2,
                    "timezone": "UTC",
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            current = data.get("current", {})
            code = current.get("weather_code")
            wind = current.get("wind_speed_10m")
            sources.append("Open-Meteo")

            if code in {95, 96, 99}:
                alerts.append("Thunderstorm indicated by weather-code forecast.")
            if wind is not None and float(wind) >= 45:
                alerts.append(f"Strong wind condition indicated ({wind} km/h).")
        except Exception as exc:
            errors.append(f"Open-Meteo hazard fallback failed: {exc}")

        level = "high" if alerts else "low"
        return {
            "agent": "disaster_agent",
            "status": "partial" if errors and not alerts else "success",
            "location": {"latitude": lat, "longitude": lon},
            "timestamp": now,
            "data": {
                "alerts": alerts,
                "alert_count": len(alerts),
                "imd_configured": bool(imd_url),
            },
            "assessment": {
                "risk_level": level,
                "summary": " ".join(alerts) if alerts else "No hazard signal was returned by the configured sources.",
            },
            "sources": [{"name": s, "timestamp": now} for s in sources],
            "confidence": 0.90 if imd_url and not errors else 0.70,
            "errors": errors,
        }

    @staticmethod
    def _extract_alerts(data: Any) -> list[str]:
        if isinstance(data, list):
            return [str(x) for x in data[:10]]
        if isinstance(data, dict):
            raw = data.get("alerts") or data.get("warnings") or data.get("data") or []
            if isinstance(raw, list):
                return [str(x.get("description", x)) if isinstance(x, dict) else str(x) for x in raw[:10]]
        return []
