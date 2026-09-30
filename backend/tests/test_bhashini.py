import os

from backend.services.bhashini import BhashiniService


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._payload


def test_bhashini_translation_uses_dynamic_service_and_inference_key(monkeypatch):
    monkeypatch.setenv("BHASHINI_USER_ID", "user")
    monkeypatch.setenv("BHASHINI_ULCA_API_KEY", "ulca")
    monkeypatch.setenv("BHASHINI_PIPELINE_ID", "pipeline")
    monkeypatch.delenv("BHASHINI_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("BHASHINI_TRANSLATION_SERVICE_ID", raising=False)

    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json))
        if "getModelsPipeline" in url:
            return FakeResponse({
                "pipelineResponseConfig": [{
                    "taskType": "translation",
                    "config": [{
                        "serviceId": "fake-service",
                        "language": {"sourceLanguage": "hi", "targetLanguage": "en"},
                    }],
                }],
                "pipelineInferenceAPIEndPoint": {
                    "callbackUrl": "https://fake-inference",
                    "inferenceApiKey": {"value": "fake-inference-key"},
                },
            })
        return FakeResponse({
            "pipelineResponse": [{
                "taskType": "translation",
                "output": [{"target": "Is it safe to fish tomorrow?"}],
            }]
        })

    monkeypatch.setattr("backend.services.bhashini.requests.post", fake_post)

    service = BhashiniService(timeout=1)
    translated = service.translate("क्या कल मछली पकड़ना सुरक्षित है?", "hi", "en")

    assert translated == "Is it safe to fish tomorrow?"
    assert len(calls) == 2
    assert calls[0][1]["userID"] == "user"
    assert calls[0][1]["ulcaApiKey"] == "ulca"
    assert calls[1][1]["Authorization"] == "fake-inference-key"
    assert calls[1][2]["pipelineTasks"][0]["config"]["serviceId"] == "fake-service"


def test_bhashini_language_detection_parses_response(monkeypatch):
    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "inference")

    def fake_post(url, headers, json, timeout):
        return FakeResponse({
            "pipelineResponse": [{
                "taskType": "txt-lang-detection",
                "output": [{"langCode": "kn", "confidence": 0.99}],
            }]
        })

    monkeypatch.setattr("backend.services.bhashini.requests.post", fake_post)

    service = BhashiniService(timeout=1)
    assert service.detect_language("ನಾಳೆ ಮೀನುಗಾರಿಕೆ ಸುರಕ್ಷಿತವೇ?") == "kn"
