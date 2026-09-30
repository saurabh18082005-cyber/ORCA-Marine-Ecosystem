"""BHASHINI text-language detection and text-to-text translation for ORCA.

The implementation follows the current BHASHINI flow:
1. Use the ULCA pipeline-config endpoint with BHASHINI_USER_ID + BHASHINI_ULCA_API_KEY.
2. Read the serviceId and inference endpoint/key returned by the config call.
3. Send the actual text inference to Dhruva.

An optional BHASHINI_INFERENCE_API_KEY can override the key returned by config.
If BHASHINI is unavailable, callers can safely fall back to local detection and
English processing; ORCA never fabricates a translation.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

import requests

CONFIG_URL = os.getenv(
    "BHASHINI_CONFIG_URL",
    "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline",
)
DEFAULT_INFERENCE_URL = os.getenv(
    "BHASHINI_INFERENCE_URL",
    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
)
DEFAULT_TLD_SERVICE_ID = os.getenv(
    "BHASHINI_LANGUAGE_DETECTION_SERVICE_ID",
    "ai4bharat/indic-lang-detect--gpu-t4",
)

# BHASHINI's public portal currently lists 30+ languages/services. This is the
# UI validation set; actual translation availability is checked dynamically by
# the configured pipeline for each source/target pair.
SUPPORTED_LANGUAGES = {
    "as": "Assamese", "bn": "Bengali", "brx": "Bodo", "doi": "Dogri",
    "en": "English", "gu": "Gujarati", "hi": "Hindi", "kn": "Kannada",
    "ks": "Kashmiri", "kok": "Konkani", "mai": "Maithili", "ml": "Malayalam",
    "mni": "Manipuri", "mr": "Marathi", "ne": "Nepali", "or": "Odia",
    "pa": "Punjabi", "sa": "Sanskrit", "sat": "Santali", "sd": "Sindhi",
    "ta": "Tamil", "te": "Telugu", "ur": "Urdu", "tcy": "Tulu",
    "bho": "Bhojpuri", "awa": "Awadhi", "raj": "Rajasthani",
    "mizo": "Mizo", "khasi": "Khasi", "si": "Sinhala",
}


class BhashiniService:
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._service_cache: Dict[Tuple[str, str], str] = {}
        self._detection_service_id: Optional[str] = None
        self._inference_url: str = DEFAULT_INFERENCE_URL
        self._inference_key: Optional[str] = os.getenv("BHASHINI_INFERENCE_API_KEY") or None
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        # ULCA credentials are sufficient because the inference key can be
        # obtained from the pipeline config response.
        return bool(os.getenv("BHASHINI_USER_ID") and os.getenv("BHASHINI_ULCA_API_KEY")) or bool(self._inference_key)

    def _config_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "userID": os.getenv("BHASHINI_USER_ID", ""),
            "ulcaApiKey": os.getenv("BHASHINI_ULCA_API_KEY", ""),
        }

    def _inference_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": self._inference_key or "",
        }

    def _pipeline_config(self, tasks: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not os.getenv("BHASHINI_USER_ID") or not os.getenv("BHASHINI_ULCA_API_KEY"):
            return None

        payload: Dict[str, Any] = {"pipelineTasks": tasks}
        pipeline_id = os.getenv("BHASHINI_PIPELINE_ID")
        if pipeline_id:
            payload["pipelineRequestConfig"] = {"pipelineId": pipeline_id}

        try:
            response = requests.post(
                CONFIG_URL,
                headers=self._config_headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            endpoint = data.get("pipelineInferenceAPIEndPoint") or {}
            callback = endpoint.get("callbackUrl")
            inference = endpoint.get("inferenceApiKey") or {}
            key = inference.get("value")
            if callback:
                self._inference_url = callback
            if key:
                self._inference_key = key
            return data
        except Exception:
            return None

    def detect_language(self, text: str) -> Optional[str]:
        if not text or not text.strip() or not self.configured:
            return None

        # TLD can be called directly with the documented service ID. If the
        # configured ULCA pipeline supplies a different TLD service, prefer it.
        service_id = self._detection_service_id or DEFAULT_TLD_SERVICE_ID
        if not self._inference_key and os.getenv("BHASHINI_USER_ID"):
            config = self._pipeline_config([
                {"taskType": "txt-lang-detection", "config": {"serviceId": service_id}}
            ])
            if config:
                service_id = self._extract_service_id(config, "txt-lang-detection") or service_id
                self._detection_service_id = service_id

        if not self._inference_key:
            return None

        payload = {
            "pipelineTasks": [{
                "taskType": "txt-lang-detection",
                "config": {"serviceId": service_id},
            }],
            "inputData": {"input": [{"source": text}]},
        }
        try:
            response = requests.post(
                self._inference_url,
                headers=self._inference_headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return self._parse_detected_language(response.json())
        except Exception:
            return None

    def translate(self, text: str, source: str, target: str) -> Optional[str]:
        if not text or not text.strip() or source == target:
            return text
        if not self.configured:
            return None

        source = source.lower().strip()
        target = target.lower().strip()
        cache_key = (source, target)
        service_id = self._service_cache.get(cache_key)

        if not service_id:
            # If the user explicitly supplies a fixed service ID, use it.
            service_id = os.getenv("BHASHINI_TRANSLATION_SERVICE_ID") or None

        if not service_id:
            config = self._pipeline_config([{
                "taskType": "translation",
                "config": {
                    "language": {
                        "sourceLanguage": source,
                        "targetLanguage": target,
                    }
                },
            }])
            if config:
                service_id = self._find_translation_service(config, source, target)

        if not service_id or not self._inference_key:
            return None

        payload = {
            "pipelineTasks": [{
                "taskType": "translation",
                "config": {
                    "language": {
                        "sourceLanguage": source,
                        "targetLanguage": target,
                    },
                    "serviceId": service_id,
                },
            }],
            "inputData": {"input": [{"source": text}]},
        }

        try:
            response = requests.post(
                self._inference_url,
                headers=self._inference_headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            translated = self._parse_translation(response.json())
            if translated:
                with self._lock:
                    self._service_cache[cache_key] = service_id
            return translated
        except Exception:
            return None

    @staticmethod
    def _extract_service_id(data: Dict[str, Any], task_type: str) -> Optional[str]:
        for task in data.get("pipelineResponseConfig", []):
            if task.get("taskType") != task_type:
                continue
            for cfg in task.get("config", []):
                if cfg.get("serviceId"):
                    return cfg["serviceId"]
        return None

    @classmethod
    def _find_translation_service(
        cls, data: Dict[str, Any], source: str, target: str
    ) -> Optional[str]:
        for task in data.get("pipelineResponseConfig", []):
            if task.get("taskType") != "translation":
                continue
            for cfg in task.get("config", []):
                lang = cfg.get("language") or {}
                if (
                    lang.get("sourceLanguage") == source
                    and lang.get("targetLanguage") == target
                    and cfg.get("serviceId")
                ):
                    return cfg["serviceId"]
        return None

    @staticmethod
    def _parse_detected_language(data: Dict[str, Any]) -> Optional[str]:
        for task in data.get("pipelineResponse", []):
            if task.get("taskType") not in ("txt-lang-detection", "language-detection"):
                continue
            output = task.get("output") or task.get("outputs") or []
            if not output:
                continue
            item = output[0] if isinstance(output, list) else output
            for key in ("langCode", "languageCode", "language", "lang"):
                value = item.get(key) if isinstance(item, dict) else None
                if isinstance(value, dict):
                    value = value.get("code") or value.get("languageCode")
                if value:
                    return str(value).lower().split("-")[0]
        return None

    @staticmethod
    def _parse_translation(data: Dict[str, Any]) -> Optional[str]:
        for task in data.get("pipelineResponse", []):
            if task.get("taskType") != "translation":
                continue
            output = task.get("output") or task.get("outputs") or []
            if not output:
                continue
            item = output[0] if isinstance(output, list) else output
            if isinstance(item, dict):
                for key in ("target", "translatedText", "translation"):
                    value = item.get(key)
                    if value is not None:
                        return str(value)
        return None


bhashini_service = BhashiniService()
