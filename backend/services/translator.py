"""ORCA multilingual NLP service.

Primary path: BHASHINI text language detection + NMT.
Fallback path: local Unicode script detection. No fake translation is returned.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.bhashini import bhashini_service, SUPPORTED_LANGUAGES


class MultilingualTranslator:
    SUPPORTED_LANGUAGES = SUPPORTED_LANGUAGES


    _FALLBACK_TEMPLATES = {}

    _SCRIPT_RANGES = [
        (0x0C80, 0x0CFF, "kn"), (0x0B80, 0x0BFF, "ta"),
        (0x0C00, 0x0C7F, "te"), (0x0D00, 0x0D7F, "ml"),
        (0x0980, 0x09FF, "bn"), (0x0A80, 0x0AFF, "gu"),
        (0x0B00, 0x0B7F, "or"), (0x0A00, 0x0A7F, "pa"),
        (0x0900, 0x097F, "hi"),
    ]

    def detect_language(self, text: str, default_code: str = "en") -> str:
        detected = bhashini_service.detect_language(text)
        if detected in self.SUPPORTED_LANGUAGES:
            return detected

        if not text:
            return default_code if default_code in self.SUPPORTED_LANGUAGES else "en"

        for char in text:
            cp = ord(char)
            for lo, hi, code in self._SCRIPT_RANGES:
                if lo <= cp <= hi:
                    return code

        return default_code if default_code in self.SUPPORTED_LANGUAGES and default_code != "auto" else "en"

    def translate_query_to_english(self, user_query: str, language_code: str) -> str:
        if not user_query or language_code == "en":
            return user_query
        translated = bhashini_service.translate(user_query, language_code, "en")
        # Never send a fake marker to the agents. If translation is unavailable,
        # preserve the original query and let the agent fallbacks operate.
        return translated or user_query

    def translate_recommendation(
        self,
        base_recommendation: str,
        risk_level: str,
        target_lang: str,
        specific_details: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not base_recommendation or not target_lang or target_lang == "en":
            return base_recommendation
        translated = bhashini_service.translate(base_recommendation, "en", target_lang)
        if translated:
            return translated
        fallback = self._FALLBACK_TEMPLATES.get(risk_level.upper(), {}).get(target_lang)
        return fallback or base_recommendation


translator_service = MultilingualTranslator()
