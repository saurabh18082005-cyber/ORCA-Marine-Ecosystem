from __future__ import annotations
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import requests


class FisheriesAgent:
    """
    PFZ/fisheries intelligence.

    INCOIS PFZ bulletins are portal/bulletin based rather than a simple
    stable REST endpoint. Configure INCOIS_PFZ_BULLETIN_URL with an approved
    bulletin/text endpoint. The parser extracts coordinates when possible.
    No synthetic PFZ is created when the official bulletin is unavailable.
    """

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def analyze(self, lat: float, lon: float) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        url = os.getenv(
            "INCOIS_PFZ_BULLETIN_URL",
            "https://www.incois.gov.in/MarineFisheries/TextDataHome?mfid=1&request_locale=en",
        )
        wms_url = os.getenv(
            "INCOIS_PFZ_WMS_URL",
            "https://incois.gov.in/geoportal/MFASPFZ/index.html",
        )
        errors = []
        zones = []

        if url:
            try:
                r = requests.get(url, timeout=self.timeout)
                r.raise_for_status()
                zones = self._parse_coordinates(r.text)
            except Exception as exc:
                errors.append(f"INCOIS PFZ bulletin fetch failed: {exc}")

        nearest = None
        if zones:
            nearest = min(
                zones,
                key=lambda z: ((z["latitude"] - lat) ** 2 + (z["longitude"] - lon) ** 2) ** 0.5,
            )

        data = {
            "pfz_available": bool(zones),
            "pfz_zone_count": len(zones),
            "nearest_pfz": nearest,
            "source_configured": True,
            "wms_url": wms_url,
            "source_url": url,
        }

        return {
            "agent": "fisheries_agent",
            "status": "success" if zones else ("partial" if errors else "unavailable"),
            "location": {"latitude": lat, "longitude": lon},
            "timestamp": now,
            "data": data,
            "assessment": {
                "risk_level": "low",
                "summary": (
                    f"{len(zones)} PFZ coordinate candidates parsed from the configured INCOIS bulletin."
                    if zones else
                    "Official INCOIS PFZ source is reachable only through the configured public bulletin/WebGIS; no parseable PFZ coordinates were returned by the current endpoint."
                ),
            },
            "sources": [{"name": "INCOIS PFZ Advisory", "timestamp": now}],
            "confidence": 0.90 if zones else 0.40,
            "errors": errors,
        }

    @staticmethod
    def _parse_coordinates(text: str) -> list[dict[str, float]]:
        # Conservative decimal-degree parser. It intentionally does not
        # convert ambiguous degree/minute/second text without a known format.
        pairs = re.findall(
            r"(?<!\d)([-+]?\d{1,2}\.\d{2,6})\s*[,/ ]\s*([-+]?\d{1,3}\.\d{2,6})(?!\d)",
            text,
        )
        zones = []
        for a, b in pairs[:200]:
            lat, lon = float(a), float(b)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                zones.append({"latitude": lat, "longitude": lon})
        return zones
