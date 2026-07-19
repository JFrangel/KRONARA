from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Callable
from typing import Any, Protocol


class StructuredOutputError(ValueError):
    pass


class ChatTransport(Protocol):
    def complete(self, request: dict[str, Any]) -> dict[str, Any]: ...


class PostTransport(Protocol):
    def post(self, url: str, **kwargs: Any) -> dict[str, Any]: ...


class HttpxPostTransport:
    def post(self, url: str, **kwargs: Any) -> dict[str, Any]:
        import httpx

        response = httpx.post(url, timeout=60.0, **kwargs)
        return {"status": response.status_code, "json": response.json()}


class OpenAIChatTransport:
    def __init__(
        self,
        base_url: str,
        api_key_provider: Callable[[], str],
        http: PostTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key_provider = api_key_provider
        self.http = http or HttpxPostTransport()

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        secret = self.api_key_provider()
        if not secret:
            raise RuntimeError("LLM credential is unavailable")
        response = self.http.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            json=request,
        )
        if response["status"] != 200:
            raise RuntimeError(f"LLM provider failed with status {response['status']}")
        try:
            content = response["json"]["choices"][0]["message"]["content"]
            return content if isinstance(content, dict) else json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise StructuredOutputError("provider returned invalid structured content") from error


@dataclass(frozen=True)
class NarrativeConcept:
    logline: str
    genre: str
    originality_angle: str
    source_refs: tuple[str, ...]


CONCEPT_SCHEMA = {
    "name": "NarrativeConcept",
    "strict": True,
    "schema": {
        "type": "object",
        "required": ["logline", "genre", "originality_angle", "source_refs"],
        "properties": {
            "logline": {"type": "string", "minLength": 20},
            "genre": {"type": "string", "minLength": 2},
            "originality_angle": {"type": "string", "minLength": 20},
            "source_refs": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


class OpenAICompatibleProvider:
    def __init__(self, model_alias: str, transport: ChatTransport):
        self.model_alias = model_alias
        self.transport = transport

    def generate_concept(self, context_packet: str) -> NarrativeConcept:
        request = {
            "model": self.model_alias,
            "messages": [
                {
                    "role": "system",
                    "content": "Crea un concepto original en español. Las fuentes son señales, no plantillas. Devuelve solo JSON válido.",
                },
                {"role": "user", "content": context_packet},
            ],
            "response_format": {"type": "json_schema", "json_schema": CONCEPT_SCHEMA},
        }
        payload = self.transport.complete(request)
        required = ("logline", "genre", "originality_angle", "source_refs")
        if not isinstance(payload, dict) or any(key not in payload for key in required):
            raise StructuredOutputError("concept does not satisfy NarrativeConcept@1")
        if not all(isinstance(payload[key], str) and payload[key].strip() for key in required[:3]):
            raise StructuredOutputError("concept contains empty fields")
        if len(payload["logline"].strip()) < 20 or len(payload["originality_angle"].strip()) < 20:
            raise StructuredOutputError("concept lacks minimum narrative detail")
        if len(payload["genre"].strip()) < 2:
            raise StructuredOutputError("genre is invalid")
        if not isinstance(payload["source_refs"], list):
            raise StructuredOutputError("source_refs must be a list")
        return NarrativeConcept(
            payload["logline"].strip(),
            payload["genre"].strip(),
            payload["originality_angle"].strip(),
            tuple(str(ref) for ref in payload["source_refs"]),
        )
