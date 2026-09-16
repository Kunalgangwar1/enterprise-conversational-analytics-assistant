"""Network-free fake implementing the application LLM contract."""

from typing import Any

from pydantic import BaseModel

from app.llm.base import StructuredModel
from app.llm.models import LLMRequest, LLMResponse


class FakeLLMClient:
    """Return configured deterministic text and structured payloads."""

    def __init__(
        self,
        *,
        text: str = "deterministic response",
        structured_payload: dict[str, Any] | None = None,
        structured_payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        if structured_payload is not None and structured_payloads is not None:
            raise ValueError("Configure one structured payload mode")
        self._text = text
        self._structured_payload = structured_payload or {}
        self._structured_payloads = tuple(structured_payloads) if structured_payloads else None
        self._structured_payload_index = 0
        self.requests: list[LLMRequest] = []
        self.structured_response_models: list[type[BaseModel]] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            text=self._text,
            provider="test_fake",
            model="deterministic-test-model",
            elapsed_ms=0,
        )

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        self.requests.append(request)
        self.structured_response_models.append(response_model)
        payload = self._structured_payload
        if self._structured_payloads is not None:
            if self._structured_payload_index >= len(self._structured_payloads):
                raise AssertionError("No configured structured fake response remains")
            payload = self._structured_payloads[self._structured_payload_index]
            self._structured_payload_index += 1
        return response_model.model_validate(payload)


class FakeStructuredAnswer(BaseModel):
    """Small reusable structured response used by fake-client tests."""

    answer: str
