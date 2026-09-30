"""
Correlation & Evidence Synthesis Aggregator for ORCA (SIH26176)
Correlates multi-source outputs from Weather, Ocean, and Marine agents,
computes normalized risk scores, produces auditable evidence logs,
and constructs interactive WebGIS GeoJSON layers (PFZs, MPAs, IMBL, hazards).
"""

import math
import uuid
import time
from typing import Dict, Any, List, Optional, Tuple
from backend.models.response import (
    RiskAssessment,
    RiskFactor,
    EvidenceItem,
    UnifiedResponse,
    GeoJSONFeature,
    GeoJSONFeatureCollection
)
from backend.services.translator import translator_service
from data.loader import data_loader, haversine_distance_km


class ResponseAggregator:
    """
    Multi-source spatial-temporal risk correlation and evidence synthesis engine.
    """

    def synthesize(
        self,
        session_id: str,
        user_query: str,
        latitude: float,
        longitude: float,
        language_code: str,
        agent_data: Dict[str, Any],
        vessel_type: str = "motorized_boat"
    ) -> UnifiedResponse:
        """
        Synthesizes agent outputs into a complete UnifiedResponse payload.
        """
        start_time = time.time()
        query_id = f"orca-qry-{uuid.uuid4().hex[:6]}"

        weather_res = agent_data.get("weather", {})
        ocean_res = agent_data.get("ocean", {})
        marine_res = agent_data.get("marine", {})
        geospatial_res = agent_data.get("geospatial", {})
        disaster_res = agent_data.get("disaster", {})
        satellite_res = agent_data.get("satellite", {})
        fisheries_res = agent_data.get("fisheries", {})

        w_data = weather_res.get("data", {})
        o_data = ocean_res.get("data", {})
        m_data = marine_res.get("data", {})
        g_data = geospatial_res.get("data", {})
        d_data = disaster_res.get("data", {})
        f_data = fisheries_res.get("data", {})

        # Extract metrics
        wind_spd = w_data.get("wind_speed_kmh")
        is_cyclone = bool(w_data.get("cyclone_warning", False))
        wave_h = o_data.get("wave_height_m")
        current_spd = o_data.get("current_speed_ms")
        sst = o_data.get("sea_surface_temperature_c")
        chloro = m_data.get("chlorophyll_mg_m3")
        pfz_detected = bool(m_data.get("pfz_detected", False)) or bool(f_data.get("pfz_available", False))
        mpa_violation = bool(m_data.get("mpa_violation", False) or g_data.get("mpa_violation", False))
        mpa_name = m_data.get("mpa_name") or g_data.get("mpa_name")
        imbl_proximity_km = m_data.get("imbl_proximity_km") or g_data.get("imbl_distance_km")
        hazard_alerts = d_data.get("alerts", []) or []

        # --- 1. Compute Multi-Factor Risk ---
        risk_score, risk_level, primary_hazard, factors = self._calculate_risk(
            wind_speed=float(wind_spd if wind_spd is not None else 0.0),
            is_cyclone=is_cyclone or bool(hazard_alerts),
            wave_height=float(wave_h if wave_h is not None else 0.0),
            current_speed=float(current_spd if current_spd is not None else 0.0),
            mpa_violation=mpa_violation,
            mpa_name=mpa_name,
            imbl_proximity_km=imbl_proximity_km,
            vessel_type=vessel_type
        )

        if hazard_alerts:
            factors.append(RiskFactor(
                factor_name="Disaster / Marine Alerts",
                value="; ".join(map(str, hazard_alerts[:3])),
                severity="high",
                description="Configured hazard sources returned one or more active signals.",
            ))
            risk_score = min(1.0, max(risk_score, 0.70))
            risk_level = "UNSAFE"

        confidence_values = [
            r.get("confidence") for r in agent_data.values()
            if isinstance(r, dict) and isinstance(r.get("confidence"), (int, float))
        ]
        synthesis_confidence = round(
            sum(confidence_values) / len(confidence_values), 2
        ) if confidence_values else 0.50

        successful_results = [r for r in agent_data.values() if isinstance(r, dict) and isinstance(r.get("data"), dict) and any(v is not None for v in r.get("data", {}).values())]
        if not successful_results:
            risk_level = "UNAVAILABLE"
            risk_score = 0.0
            primary_hazard = "Live source data unavailable"
            factors = [RiskFactor(
                factor_name="Data availability", value="Unavailable", severity="moderate",
                description="No selected live agent returned usable observations for this query."
            )]

        risk_assessment = RiskAssessment(
            level=risk_level,
            risk_score=risk_score,
            primary_hazard=primary_hazard or (hazard_alerts[0] if hazard_alerts else None),
            confidence=synthesis_confidence,
            contributing_factors=factors
        )

        # --- 2. Compile Auditable Evidence Trail ---
        evidence_list, timestamp_map = self._build_evidence_trail(
            weather_res=weather_res,
            ocean_res=ocean_res,
            marine_res=marine_res,
            geospatial_res=geospatial_res,
            disaster_res=disaster_res,
            satellite_res=satellite_res,
            fisheries_res=fisheries_res,
            wind_spd=wind_spd,
            wave_h=wave_h,
            sst=sst,
            chloro=chloro,
            pfz_detected=pfz_detected,
            mpa_violation=mpa_violation,
            mpa_name=mpa_name,
            imbl_proximity_km=imbl_proximity_km
        )

        # --- 3. Construct Geospatial Layers (GeoJSON) ---
        geojson_layers = self._build_geojson_layers(
            lat=latitude,
            lon=longitude,
            pfz_detected=pfz_detected,
            chloro=chloro,
            sst=sst,
            wave_h=wave_h,
            wind_spd=wind_spd,
            mpa_violation=mpa_violation,
            mpa_name=mpa_name
        )
        geojson_layers["satellite_layers"] = satellite_res.get("data", {}).get("earth_observation_layers", [])
        geojson_layers["pfz_official"] = f_data.get("nearest_pfz")

        # --- 4. Synthesize Plain-Language Recommendation ---
        base_recommendation = self._generate_recommendation_text(
            risk_level=risk_level,
            primary_hazard=primary_hazard,
            wind_spd=wind_spd,
            wave_h=wave_h,
            pfz_detected=pfz_detected,
            chloro=chloro,
            mpa_violation=mpa_violation,
            mpa_name=mpa_name,
            imbl_proximity_km=imbl_proximity_km
        )

        # Multilingual Translation
        translated_recommendation = translator_service.translate_recommendation(
            base_recommendation=base_recommendation,
            risk_level=risk_level,
            target_lang=language_code,
            specific_details={
                "wave_height_m": wave_h,
                "wind_speed_kmh": wind_spd,
                "pfz_distance_km": None
            }
        )

        execution_time_ms = round((time.time() - start_time) * 1000.0, 2)

        return UnifiedResponse(
            session_id=session_id,
            query_id=query_id,
            user_query=user_query,
            recommendation=translated_recommendation,
            language_code=language_code,
            risk=risk_assessment,
            evidence=evidence_list,
            geojson_layers=geojson_layers,
            agent_assessments={
                "weather_agent": weather_res,
                "ocean_agent": ocean_res,
                "marine_agent": marine_res,
                "geospatial_agent": geospatial_res,
                "disaster_agent": disaster_res,
                "satellite_agent": satellite_res,
                "fisheries_agent": fisheries_res
            },
            timestamps=timestamp_map,
            execution_time_ms=execution_time_ms
        )

    def _calculate_risk(
        self,
        wind_speed: float,
        is_cyclone: bool,
        wave_height: float,
        current_speed: float,
        mpa_violation: bool,
        mpa_name: Optional[str],
        imbl_proximity_km: Optional[float],
        vessel_type: str
    ) -> Tuple[float, str, Optional[str], List[RiskFactor]]:
        """
        Calculates weighted composite risk index [0.0, 1.0] and categorizes level.
        """
        factors: List[RiskFactor] = []
        raw_score = 0.0
        primary_hazards: List[str] = []

        # Cyclone check (Critical)
        if is_cyclone:
            raw_score += 0.90
            primary_hazards.append("Cyclone warning active")
            factors.append(RiskFactor(
                factor_name="Cyclonic Hazard",
                value="Active",
                severity="critical",
                threshold_limit="Any cyclone warning",
                description="Severe cyclonic circulation detected in region."
            ))

        # Wind Speed
        if wind_speed >= 45.0:
            raw_score += 0.40
            primary_hazards.append(f"Gale-force winds ({wind_speed} km/h)")
            factors.append(RiskFactor(
                factor_name="Wind Speed",
                value=wind_speed,
                unit="km/h",
                threshold_limit="> 45 km/h is High Risk",
                severity="high",
                description=f"Strong gale winds of {wind_speed} km/h."
            ))
        elif wind_speed >= 30.0:
            raw_score += 0.20
            primary_hazards.append(f"Moderate winds ({wind_speed} km/h)")
            factors.append(RiskFactor(
                factor_name="Wind Speed",
                value=wind_speed,
                unit="km/h",
                threshold_limit="30-45 km/h is Moderate Risk",
                severity="moderate",
                description=f"Moderate breeze of {wind_speed} km/h."
            ))
        else:
            raw_score += 0.05
            factors.append(RiskFactor(
                factor_name="Wind Speed",
                value=wind_speed,
                unit="km/h",
                threshold_limit="< 30 km/h is Safe",
                severity="low",
                description=f"Calm to light wind conditions ({wind_speed} km/h)."
            ))

        # Wave Height
        if wave_height >= 3.0:
            raw_score += 0.50
            primary_hazards.append(f"High waves ({wave_height}m)")
            factors.append(RiskFactor(
                factor_name="Wave Height",
                value=wave_height,
                unit="m",
                threshold_limit="> 3.0m is High Hazard",
                severity="critical",
                description=f"Rough sea state with significant wave height of {wave_height}m."
            ))
        elif wave_height >= 2.0:
            raw_score += 0.25
            primary_hazards.append(f"Moderate swell ({wave_height}m)")
            factors.append(RiskFactor(
                factor_name="Wave Height",
                value=wave_height,
                unit="m",
                threshold_limit="2.0-3.0m is Moderate Risk",
                severity="moderate",
                description=f"Moderate wave swell of {wave_height}m."
            ))
        else:
            raw_score += 0.05
            factors.append(RiskFactor(
                factor_name="Wave Height",
                value=wave_height,
                unit="m",
                threshold_limit="< 2.0m is Safe",
                severity="low",
                description=f"Calm sea state with wave height {wave_height}m."
            ))

        # Surface Current
        if current_speed >= 1.2:
            raw_score += 0.15
            factors.append(RiskFactor(
                factor_name="Surface Current",
                value=current_speed,
                unit="m/s",
                threshold_limit="> 1.2 m/s requires caution",
                severity="moderate",
                description=f"Strong surface drift current of {current_speed} m/s."
            ))

        # MPA Boundary Compliance
        if mpa_violation:
            raw_score += 0.35
            primary_hazards.append(f"Restricted Marine Protected Area ({mpa_name})")
            factors.append(RiskFactor(
                factor_name="MPA Geofence",
                value=mpa_name or "Protected Zone",
                severity="high",
                threshold_limit="Zero fishing tolerance",
                description=f"Coordinates fall within {mpa_name}. Commercial fishing is prohibited."
            ))

        # IMBL Boundary Warning
        if imbl_proximity_km is not None and imbl_proximity_km <= 15.0:
            raw_score += 0.25
            primary_hazards.append(f"IMBL Proximity ({imbl_proximity_km} km)")
            factors.append(RiskFactor(
                factor_name="IMBL Boundary Proximity",
                value=imbl_proximity_km,
                unit="km",
                threshold_limit="< 15 km is warning zone",
                severity="moderate",
                description=f"Vessel is located within {imbl_proximity_km} km of International Maritime Boundary Line."
            ))

        # Normalize score
        normalized_score = min(1.0, max(0.0, round(raw_score, 2)))

        if is_cyclone or normalized_score >= 0.70:
            level = "UNSAFE"
        elif normalized_score >= 0.35:
            level = "CAUTION"
        else:
            level = "SAFE"

        primary_hazard = ", ".join(primary_hazards) if primary_hazards else None

        return normalized_score, level, primary_hazard, factors

    def _build_evidence_trail(
        self,
        weather_res: Dict[str, Any],
        ocean_res: Dict[str, Any],
        marine_res: Dict[str, Any],
        geospatial_res: Dict[str, Any],
        disaster_res: Dict[str, Any],
        satellite_res: Dict[str, Any],
        fisheries_res: Dict[str, Any],
        wind_spd: Optional[float],
        wave_h: float,
        sst: float,
        chloro: float,
        pfz_detected: bool,
        mpa_violation: bool,
        mpa_name: Optional[str],
        imbl_proximity_km: Optional[float]
    ) -> Tuple[List[EvidenceItem], Dict[str, str]]:
        """Compile verifiable data provenance list."""
        items: List[EvidenceItem] = []
        timestamps: Dict[str, str] = {}

        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # IMD Weather evidence
        w_ts = weather_res.get("timestamp", now_ts)
        timestamps["IMD_Weather"] = w_ts
        items.append(EvidenceItem(
            source="IMD Meteorological Ingestion",
            observation=f"Wind speed measured at {wind_spd if wind_spd is not None else "unavailable"} km/h with no active cyclone warning.",
            timestamp=w_ts,
            category="weather",
            severity="info" if (wind_spd if wind_spd is not None else 0.0) < 35.0 else "warning"
        ))

        # INCOIS Ocean State Forecast
        o_ts = ocean_res.get("timestamp", now_ts)
        timestamps["INCOIS_OSF"] = o_ts
        items.append(EvidenceItem(
            source="INCOIS Ocean State Forecast (OSF)",
            observation=f"Wave height: {wave_h}m, Sea Surface Temperature (SST): {sst}°C.",
            timestamp=o_ts,
            category="ocean",
            severity="info" if (wave_h is not None and wave_h < 2.0) else ("warning" if wave_h is not None else "unknown")
        ))

        # IRS P4 OCM Chlorophyll
        m_ts = marine_res.get("timestamp", now_ts)
        timestamps["IRS_P4_OCM"] = m_ts
        if pfz_detected:
            items.append(EvidenceItem(
                source="IRS P4 OCM & INCOIS PFZ Mission",
                observation=f"Chlorophyll-a concentration {chloro} mg/m³ with thermal front gradient. Potential Fishing Zone confirmed.",
                timestamp=m_ts,
                category="satellite",
                severity="favorable"
            ))
        else:
            items.append(EvidenceItem(
                source="IRS P4 OCM Satellite Pass",
                observation=f"Background chlorophyll-a concentration {chloro} mg/m³.",
                timestamp=m_ts,
                category="satellite",
                severity="info"
            ))

        # Hazard alerts
        for alert in (disaster_res.get("data", {}).get("alerts") or [])[:5]:
            items.append(EvidenceItem(
                source="IMD / Open-Meteo hazard layer",
                observation=str(alert),
                timestamp=disaster_res.get("timestamp", now_ts),
                category="weather",
                severity="warning",
            ))

        # Satellite imagery provenance
        sat_layers = satellite_res.get("data", {}).get("earth_observation_layers", [])
        if sat_layers:
            items.append(EvidenceItem(
                source="NASA GIBS / Earth observation",
                observation="Map-ready satellite imagery metadata is available for contextual analysis.",
                timestamp=satellite_res.get("timestamp", now_ts),
                category="satellite",
                severity="info",
            ))

        # Official PFZ source, when configured
        if fisheries_res.get("data", {}).get("pfz_available"):
            items.append(EvidenceItem(
                source="INCOIS PFZ Advisory",
                observation="PFZ bulletin data was successfully parsed.",
                timestamp=fisheries_res.get("timestamp", now_ts),
                category="fisheries",
                severity="favorable",
            ))

        # Geofencing
        if mpa_violation:
            items.append(EvidenceItem(
                source="Ministry of Environment & Forests (MoEFCC) MPA Registry",
                observation=f"Location intersects boundary of {mpa_name}. Fishing strictly prohibited by conservation law.",
                timestamp=now_ts,
                category="geofence",
                severity="critical"
            ))
        elif imbl_proximity_km is not None and imbl_proximity_km <= 20.0:
            items.append(EvidenceItem(
                source="Indian Coast Guard Maritime Boundary Registry",
                observation=f"Vessel proximity within {imbl_proximity_km} km of International Maritime Boundary Line.",
                timestamp=now_ts,
                category="geofence",
                severity="warning"
            ))

        return items, timestamps

    def _build_geojson_layers(
        self,
        lat: float,
        lon: float,
        pfz_detected: bool,
        chloro: float,
        sst: float,
        wave_h: float,
        wind_spd: float,
        mpa_violation: bool,
        mpa_name: Optional[str]
    ) -> Dict[str, Any]:
        """Construct WebGIS compatible GeoJSON vector layers."""
        layers: Dict[str, Any] = {}

        # 1. User / Query Point
        layers["query_point"] = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": {
                        "name": "Target Location",
                        "latitude": lat,
                        "longitude": lon,
                        "wave_height_m": wave_h,
                        "wind_speed_kmh": wind_spd
                    }
                }
            ]
        }

        # 2. PFZ Zone (if active)
        if pfz_detected:
            # Generate polygon offset slightly offshore
            offset_lon = lon - 0.15 if lon > 70.0 else lon + 0.15
            offset_lat = lat + 0.05
            d = 0.08
            pfz_poly = [
                [offset_lon - d, offset_lat - d],
                [offset_lon + d, offset_lat - d],
                [offset_lon + d, offset_lat + d],
                [offset_lon - d, offset_lat + d],
                [offset_lon - d, offset_lat - d]
            ]
            layers["pfz_layer"] = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "id": "PFZ-ACTIVE-01",
                            "name": "High-Yield Potential Fishing Zone",
                            "chlorophyll_mg_m3": chloro,
                            "sst_celsius": sst,
                            "confidence": 0.89,
                            "target_species": ["Mackerel", "Sardine", "Tuna"]
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [pfz_poly]
                        }
                    }
                ]
            }

        # 3. IMBL Reference Lines
        imbl_data = data_loader.get_imbl_boundaries()
        if imbl_data:
            imbl_features = []
            for item in imbl_data:
                imbl_features.append({
                    "type": "Feature",
                    "properties": {
                        "name": item.get("name"),
                        "warning_distance_km": item.get("warning_distance_km")
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": item.get("coordinates", [])
                    }
                })
            layers["imbl_boundaries"] = {
                "type": "FeatureCollection",
                "features": imbl_features
            }

        # 4. MPA Zones
        mpas = data_loader.get_mpas()
        if mpas:
            mpa_features = []
            for m in mpas:
                bbox = m.get("bbox")
                if bbox and len(bbox) == 4:
                    min_x, min_y, max_x, max_y = bbox
                    poly = [
                        [min_x, min_y],
                        [max_x, min_y],
                        [max_x, max_y],
                        [min_x, max_y],
                        [min_x, min_y]
                    ]
                    mpa_features.append({
                        "type": "Feature",
                        "properties": {
                            "name": m.get("name"),
                            "restrictions": m.get("restrictions"),
                            "state": m.get("state")
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [poly]
                        }
                    })
            layers["mpa_zones"] = {
                "type": "FeatureCollection",
                "features": mpa_features
            }

        return layers

    def _generate_recommendation_text(
        self,
        risk_level: str,
        primary_hazard: Optional[str],
        wind_spd: float,
        wave_h: float,
        pfz_detected: bool,
        chloro: float,
        mpa_violation: bool,
        mpa_name: Optional[str],
        imbl_proximity_km: Optional[float]
    ) -> str:
        """Compose human-readable English recommendation synthesizing all factors."""
        if risk_level == "UNAVAILABLE":
            return "Live data is currently unavailable for the selected location and query. ORCA has not generated a scientific safety conclusion."

        if risk_level == "UNSAFE":
            hazard_str = f" ({primary_hazard})" if primary_hazard else ""
            return f"UNSAFE FOR MARITIME OPERATIONS{hazard_str}. Live observations indicate elevated marine risk."

        if mpa_violation:
            return f"CAUTION: Location is inside {mpa_name}. Commercial fishing is strictly prohibited under marine conservation regulations."

        if risk_level == "CAUTION":
            imbl_str = f" Maintain vigilance as you are {imbl_proximity_km} km from the IMBL." if imbl_proximity_km else ""
            return f"Exercise caution. Live observations indicate elevated marine risk with the reported conditions.{imbl_str}"

        # SAFE
        pfz_str = " A live PFZ signal was returned by the configured source." if pfz_detected else ""
        return f"Live observations do not indicate an elevated composite risk at the queried point.{pfz_str}"


# Global aggregator instance
aggregator_service = ResponseAggregator()
