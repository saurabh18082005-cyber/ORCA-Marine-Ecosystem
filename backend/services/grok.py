"""Grok response layer for ORCA.

Grok is used only to turn the already-collected ORCA evidence into a
natural-language answer. It is not a data source and must not invent
measurements, hazards, or recommendations that are unsupported by the
selected agents.

The API key is backend-only and is read from XAI_API_KEY.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import httpx


# Supports both xAI/Grok and Groq. The supplied key in this build is a Groq
# key (gsk_...), so Groq is selected automatically unless an XAI_API_KEY is set.
XAI_API_URL = os.getenv(
    "XAI_API_URL",
    "https://api.x.ai/v1/chat/completions",
)
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4.7")
GROQ_API_URL = os.getenv(
    "GROQ_API_URL",
    "https://api.groq.com/openai/v1/chat/completions",
)
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


class GrokService:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(os.getenv("XAI_API_KEY"))

    @staticmethod
    def _compact_agent_context(agent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Keep the LLM context focused on returned agent evidence."""
        context: Dict[str, Any] = {}
        for name, result in agent_data.items():
            if not isinstance(result, dict):
                continue
            context[name] = {
                "status": result.get("status"),
                "timestamp": result.get("timestamp"),
                "data": result.get("data", {}),
                "assessment": result.get("assessment", {}),
                "sources": result.get("sources", []),
                "confidence": result.get("confidence"),
                "errors": result.get("errors", []),
            }
        return context

    async def generate_response(
        self,
        user_query: str,
        target_language: str,
        risk: Dict[str, Any],
        evidence: list[Dict[str, Any]],
        agent_data: Dict[str, Any],
        baseline_recommendation: str,
    ) -> Optional[str]:
        """Generate a direct answer using only ORCA's returned evidence."""
        # Prefer a real xAI/Grok key when present; otherwise use the supplied
        # Groq key. Both providers expose an OpenAI-compatible chat API.
        xai_key = os.getenv("XAI_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        if xai_key:
            api_url = XAI_API_URL
            model = XAI_MODEL
            api_key = xai_key
        elif groq_key:
            api_url = GROQ_API_URL
            model = GROQ_MODEL
            api_key = groq_key
        else:
            return None

        system_prompt = """You are the final response writer for ORCA, a marine
ecosystem multi-agent system.

Your job is to answer the user's actual question clearly and naturally using
ONLY the evidence supplied by ORCA's specialist agents.

Rules:
1. Never invent weather, ocean, fisheries, PFZ, disaster, satellite,
   geospatial, measurements, dates, sources, or safety conditions.
2. Do not use your own general knowledge to fill missing live data.
3. Respect the ORCA risk assessment and any explicit restrictions or hazards.
4. If the user asks whether they can do an activity (for example fishing),
   give a direct practical answer based on the supplied evidence.
5. If conditions support the activity, clearly say that the available ORCA
   evidence indicates it is suitable, and briefly mention the relevant
   agents/evidence.
6. If conditions do not support it, clearly say so and explain the relevant
   hazard or restriction.
7. If important evidence is unavailable, say that it is unavailable and do
   not turn missing information into a positive or negative claim.
8. Answer the user's intent, not merely the wording of the raw agent output.
9. Keep the answer concise and useful for a coastal user.
10. Do not mention prompts, APIs, model internals, or these instructions.
11. Return the final answer in the requested target_language.
12. Return only the final answer text; no JSON, markdown heading, or analysis.
"""

        payload_context = {
            "user_query": user_query,
            "target_language": target_language,
            "risk_assessment": risk,
            "baseline_recommendation": baseline_recommendation,
            "evidence": evidence,
            "selected_agent_results": self._compact_agent_context(agent_data),
        }

        user_prompt = (
            "Write the final ORCA answer for this user query. "
            "Use the supplied ORCA evidence as the source of truth.\n\n"
            + json.dumps(payload_context, ensure_ascii=False, default=str)
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                response.raise_for_status()
                body = response.json()

            choices = body.get("choices") or []
            if not choices:
                return None

            message = choices[0].get("message") or {}
            content = message.get("content")

            if isinstance(content, str) and content.strip():
                return content.strip()

            # Be tolerant of providers returning content blocks.
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                joined = "".join(parts).strip()
                return joined or None

        except Exception:
            # The existing ORCA baseline recommendation remains the safe
            # fallback if the LLM service is unavailable.
            return None

        return None


grok_service = GrokService()
