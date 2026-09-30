from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from data.loader import data_loader, haversine_distance_km


class GeospatialAgent:
    """Local geospatial reasoning over ORCA's reference boundaries and ports."""

    def analyze(self, lat: float, lon: float) -> Dict[str, Any]:
        port, port_distance = data_loader.find_nearest_port(lat, lon)
        mpa_name, in_mpa = data_loader.check_mpa_intersection(lat, lon)
        boundary_name, boundary_distance, in_warning = data_loader.check_imbl_proximity(lat, lon)

        layers = {
            "mpa_zones": data_loader.get_mpas(),
            "imbl_boundaries": data_loader.get_imbl_boundaries(),
        }

        findings = []
        if in_mpa:
            findings.append(f"Location intersects {mpa_name}.")
        if in_warning:
            findings.append(
                f"Location is within the configured IMBL warning zone "
                f"({boundary_distance:.1f} km from {boundary_name})."
            )

        return {
            "agent": "geospatial_agent",
            "status": "success",
            "location": {"latitude": lat, "longitude": lon},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "nearest_port": port.get("name") if port else None,
                "nearest_port_distance_km": round(port_distance, 2) if port else None,
                "mpa_violation": in_mpa,
                "mpa_name": mpa_name,
                "imbl_boundary": boundary_name,
                "imbl_distance_km": round(boundary_distance, 2) if boundary_name else None,
                "imbl_warning": in_warning,
                "layers": layers,
            },
            "assessment": {
                "risk_level": "high" if in_mpa else ("moderate" if in_warning else "low"),
                "summary": " ".join(findings) if findings else "No configured geospatial restriction detected at this point.",
            },
            "sources": [
                {"name": "ORCA reference geospatial layers", "timestamp": datetime.now(timezone.utc).isoformat()}
            ],
            "confidence": 0.95 if layers["mpa_zones"] or layers["imbl_boundaries"] else 0.60,
            "errors": [],
        }
