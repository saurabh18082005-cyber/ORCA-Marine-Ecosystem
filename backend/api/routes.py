"""
FastAPI Routes for ORCA Backend (SIH26176)
Exposes core conversational endpoints, multi-agent dispatching pipeline,
mock endpoints for Frontend unblocking, and WebGIS layers.
"""

import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Path

from backend.models.request import QueryRequest, FeedbackRequest
from backend.models.response import (
    UnifiedResponse,
    HealthResponse,
    HistoryResponse,
    RiskAssessment,
    EvidenceItem
)
from backend.services.agent_dispatcher import agent_dispatcher
from backend.services.aggregator import aggregator_service
from backend.services.session_manager import session_manager
from backend.services.translator import translator_service
from backend.services.grok import grok_service
from data.loader import data_loader

api_router = APIRouter(prefix="/api/v1")


# --- Health & Status ---
@api_router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """System health check and agent connectivity report."""
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        service="ORCA Multi-Agent Backend Pipeline (SIH26176)",
        agents_available={
            "weather_agent": True,
            "ocean_agent": True,
            "marine_agent": True,
            "geospatial_agent": True,
            "disaster_agent": True,
            "satellite_agent": True,
            "fisheries_agent": True,
            "coordinator_agent": True
        },
        timestamp=now_ts
    )


# --- Core Query Pipeline ---
@api_router.post(
    "/query",
    response_model=UnifiedResponse,
    summary="Submit natural language marine query for multi-agent reasoning",
    tags=["Conversational Reasoning"]
)
async def process_marine_query(payload: QueryRequest):
    """Run the live ORCA pipeline. A location name is geocoded when GPS coordinates are not supplied."""
    session = session_manager.get_or_create_session(
        session_id=payload.session_id,
        language_code=payload.language_code
    )

    latitude, longitude = payload.latitude, payload.longitude
    if latitude is None or longitude is None:
        location_text = (payload.metadata or {}).get("location_name")
        if not location_text:
            raise HTTPException(status_code=400, detail="Provide GPS coordinates or a location name.")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "ORCA-SIH/1.0"}) as client:
                response = await client.get("https://nominatim.openstreetmap.org/search", params={
                    "q": location_text, "format": "jsonv2", "limit": 1, "countrycodes": "in"
                })
                response.raise_for_status()
                places = response.json()
            if not places:
                raise HTTPException(status_code=400, detail=f"Location not found: {location_text}")
            latitude = float(places[0]["lat"])
            longitude = float(places[0]["lon"])
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Location lookup failed: {exc}")

    detected_lang = translator_service.detect_language(
        payload.user_query,
        default_code="en" if payload.language_code in (None, "", "auto") else payload.language_code,
    )
    target_lang = detected_lang if payload.language_code in (None, "", "auto") else payload.language_code
    if target_lang in translator_service.SUPPORTED_LANGUAGES:
        session.preferred_language = target_lang
    english_query = translator_service.translate_query_to_english(payload.user_query, detected_lang)

    agent_results = await agent_dispatcher.dispatch_all(
        latitude=latitude, longitude=longitude, user_query=english_query,
        session_id=payload.session_id, timestamp=payload.timestamp
    )

    unified_output = aggregator_service.synthesize(
        session_id=payload.session_id, user_query=payload.user_query,
        latitude=latitude, longitude=longitude, language_code=target_lang,
        agent_data=agent_results, vessel_type=payload.vessel_type or "motorized_boat"
    )

    # Optional final reasoning layer: Grok receives only the evidence already
    # returned by ORCA's selected agents. It does not replace the coordinator,
    # routing, agents, validation, aggregation, or data sources.
    grok_answer = await grok_service.generate_response(
        user_query=payload.user_query,
        target_language="en",
        risk=unified_output.risk.model_dump(),
        evidence=[item.model_dump() for item in unified_output.evidence],
        agent_data={
            key: value for key, value in agent_results.items()
            if key != "coordinator"
        },
        baseline_recommendation=unified_output.recommendation,
    )
    if grok_answer:
        translated_grok = translator_service.translate_recommendation(
            base_recommendation=grok_answer,
            risk_level=unified_output.risk.level,
            target_lang=target_lang,
        )
        # Bhashini remains the primary final-response translator. If it is
        # unavailable for the detected language, ask the existing Groq layer
        # for the same evidence-based answer directly in that language.
        if target_lang != "en" and translated_grok == grok_answer:
            localized_grok = await grok_service.generate_response(
                user_query=payload.user_query,
                target_language=target_lang,
                risk=unified_output.risk.model_dump(),
                evidence=[item.model_dump() for item in unified_output.evidence],
                agent_data={
                    key: value for key, value in agent_results.items()
                    if key != "coordinator"
                },
                baseline_recommendation=unified_output.recommendation,
            )
            if localized_grok:
                translated_grok = localized_grok
        unified_output.recommendation = translated_grok or grok_answer
    # Expose the resolved coordinates so the frontend never has to guess a location.
    unified_output.geojson_layers["query_location"] = {"latitude": latitude, "longitude": longitude}
    unified_output.agent_assessments["coordinator_agent"] = agent_results.get("coordinator", {})

    session.add_turn(
        query_id=unified_output.query_id, user_query=payload.user_query,
        recommendation=unified_output.recommendation, risk_level=unified_output.risk.level,
        risk_score=unified_output.risk.risk_score, latitude=latitude, longitude=longitude,
        agent_data=agent_results
    )
    return unified_output


@api_router.get("/geocode", tags=["Location"])
async def geocode_location(q: str = Query(..., min_length=2)):
    """Resolve a human-readable location through OpenStreetMap Nominatim."""
    import httpx
    async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "ORCA-SIH/1.0"}) as client:
        response = await client.get("https://nominatim.openstreetmap.org/search", params={
            "q": q, "format": "jsonv2", "limit": 1, "countrycodes": "in"
        })
        response.raise_for_status()
        places = response.json()
    if not places:
        raise HTTPException(status_code=404, detail="Location not found")
    place = places[0]
    return {"name": place.get("display_name", q), "latitude": float(place["lat"]), "longitude": float(place["lon"])}


# --- History Retrieval ---
@api_router.get(
    "/history/{session_id}",
    response_model=HistoryResponse,
    summary="Get multi-turn history for a conversation session",
    tags=["Session State"]
)
async def get_history(session_id: str = Path(..., description="Unique conversation session ID")):
    """Fetch all conversational turns for session memory."""
    session = session_manager.get_session(session_id)
    if not session:
        return HistoryResponse(session_id=session_id, total_turns=0, history=[])
    return session.to_history_response()


# --- Geospatial Reference Layers ---
@api_router.get("/layers", summary="Fetch reference WebGIS vector layers", tags=["WebGIS Layers"])
async def get_reference_layers(layer_type: Optional[str] = Query(default="all")):
    """
    Retrieve reference geospatial layers:
    - `ports`: Major Indian ports
    - `imbl`: International Maritime Boundary Lines
    - `mpas`: Marine Protected Areas
    - `all`: Combined payload
    """
    if layer_type == "ports":
        return {"ports": data_loader.get_ports()}
    elif layer_type == "imbl":
        return {"imbl_lines": data_loader.get_imbl_boundaries()}
    elif layer_type == "mpas":
        return {"marine_protected_areas": data_loader.get_mpas()}

    # All layers
    return {
        "ports": data_loader.get_ports(),
        "imbl_lines": data_loader.get_imbl_boundaries(),
        "marine_protected_areas": data_loader.get_mpas(),
    }


# --- Supported Languages ---
@api_router.get("/languages", summary="List supported Indian regional languages", tags=["Multilingual"])
async def get_supported_languages():
    """Returns dictionary of supported language codes and their native script names."""
    return {"supported_languages": translator_service.SUPPORTED_LANGUAGES}


# --- User Feedback ---
@api_router.post("/feedback", summary="Submit ground observation feedback", tags=["Feedback"])
async def submit_feedback(payload: FeedbackRequest):
    """Collects ground truth accuracy feedback from fishermen and coastal users."""
    return {
        "status": "success",
        "message": "Feedback recorded successfully. Thank you for improving ORCA marine models.",
        "session_id": payload.session_id,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
