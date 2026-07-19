import json

import pytest

from kronara.llm import OpenAIChatTransport, OpenAICompatibleProvider, StructuredOutputError


class FakeChatTransport:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def complete(self, request):
        self.request = request
        return self.payload


def test_provider_requests_json_schema_and_validates_concept():
    transport = FakeChatTransport(
        {
            "logline": "Una huésped descubre que su habitación no figura en los planos.",
            "genre": "paranormal",
            "originality_angle": "El edificio reescribe su registro cada noche.",
            "source_refs": ["reddit://abc"],
        }
    )
    provider = OpenAICompatibleProvider("qwen-planner", transport)

    concept = provider.generate_concept("signal packet")

    assert concept.genre == "paranormal"
    assert transport.request["response_format"]["type"] == "json_schema"


def test_provider_rejects_missing_originality_angle():
    provider = OpenAICompatibleProvider(
        "qwen-planner",
        FakeChatTransport({"logline": "x", "genre": "drama", "source_refs": []}),
    )

    with pytest.raises(StructuredOutputError):
        provider.generate_concept("signal packet")


def test_provider_enforces_minimum_narrative_detail():
    provider = OpenAICompatibleProvider(
        "qwen-planner",
        FakeChatTransport(
            {"logline": "muy corto", "genre": "drama", "originality_angle": "sin detalle", "source_refs": []}
        ),
    )

    with pytest.raises(StructuredOutputError):
        provider.generate_concept("signal packet")


class FakeHttpClient:
    def __init__(self):
        self.call = None

    def post(self, url, **kwargs):
        self.call = (url, kwargs)
        return {
            "status": 200,
            "json": {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "logline": "Una archivista descubre cartas que anticipan accidentes.",
                                    "genre": "misterio",
                                    "originality_angle": "Cada carta desaparece cuando alguien evita el accidente.",
                                    "source_refs": [],
                                }
                            )
                        }
                    }
                ]
            },
        }


def test_openai_transport_keeps_secret_outside_request_contract():
    http = FakeHttpClient()
    transport = OpenAIChatTransport(
        "https://router.example/v1", api_key_provider=lambda: "private-key", http=http
    )
    request = {"model": "qwen-planner", "messages": [], "response_format": {}}

    result = transport.complete(request)

    assert result["genre"] == "misterio"
    assert http.call[1]["headers"]["Authorization"] == "Bearer private-key"
    assert "private-key" not in repr(request)
