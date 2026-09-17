"""Network-free tests for the official Gemini LLM adapter."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors
from pydantic import BaseModel

import app.llm.gemini as gemini_module
from app.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.llm.gemini import GeminiLLMClient
from app.llm.models import LLMMessage, LLMRequest, LLMRole


class StructuredAnswer(BaseModel):
    answer: str


def _request() -> LLMRequest:
    return LLMRequest(
        messages=[
            LLMMessage(role=LLMRole.SYSTEM, content="System boundary."),
            LLMMessage(role=LLMRole.USER, content="Harmless user question."),
            LLMMessage(role=LLMRole.ASSISTANT, content="Earlier model response."),
            LLMMessage(role=LLMRole.USER, content="Current user question."),
        ],
        temperature=0.2,
    )


def _client(sdk: MagicMock, *, timer: MagicMock | None = None) -> GeminiLLMClient:
    return GeminiLLMClient(
        api_key="gemini-test-secret",
        model="gemini-test-model",
        timeout_seconds=30,
        max_retries=2,
        max_output_tokens=1_000,
        sdk_client=sdk,
        timer=timer or MagicMock(side_effect=[1.0, 1.1]),
    )


def test_gemini_sdk_uses_bounded_transport_timeout_without_nested_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = MagicMock()
    monkeypatch.setattr(gemini_module.genai, "Client", constructor)

    GeminiLLMClient(
        api_key="test-key",
        model="model",
        timeout_seconds=12.5,
        max_retries=3,
        max_output_tokens=500,
    )

    kwargs = constructor.call_args.kwargs
    assert kwargs["api_key"] == "test-key"
    assert kwargs["http_options"].timeout == 12_500
    assert kwargs["http_options"].retry_options.attempts == 1
    transport_timeout = kwargs["http_options"].client_args["timeout"]
    assert transport_timeout.connect == 5
    assert transport_timeout.read == 12.5


def test_text_response_roles_usage_and_metadata_are_normalized() -> None:
    sdk = MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(
        text="Gemini response",
        response_id="gemini-response-1",
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=5,
            total_token_count=17,
        ),
    )
    response = _client(sdk, timer=MagicMock(side_effect=[2.0, 2.125])).generate(_request())

    assert response.text == "Gemini response"
    assert response.provider == "gemini"
    assert response.model == "gemini-test-model"
    assert response.request_id == "gemini-response-1"
    assert response.usage.model_dump() == {
        "input_tokens": 12,
        "output_tokens": 5,
        "total_tokens": 17,
    }
    assert response.elapsed_ms == 125
    call = sdk.models.generate_content.call_args.kwargs
    assert call["config"].system_instruction == "System boundary."
    assert [content.role for content in call["contents"]] == ["user", "model", "user"]
    assert "System boundary." not in " ".join(
        part.text for content in call["contents"] for part in content.parts
    )
    assert call["config"].temperature is None


def test_structured_output_uses_native_response_schema() -> None:
    sdk = MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(
        parsed=StructuredAnswer(answer="validated")
    )

    result = _client(sdk).generate_structured(_request(), StructuredAnswer)

    assert result == StructuredAnswer(answer="validated")
    config = sdk.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is StructuredAnswer


def test_missing_or_invalid_structured_output_fails_without_manual_json_parsing() -> None:
    sdk = MagicMock()
    sdk.models.generate_content.return_value = SimpleNamespace(parsed={"wrong": "field"})

    with pytest.raises(LLMStructuredOutputError):
        _client(sdk).generate_structured(_request(), StructuredAnswer)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (401, LLMAuthenticationError),
        (429, LLMRateLimitError),
        (504, LLMTimeoutError),
        (500, LLMProviderError),
    ],
)
def test_gemini_errors_are_translated_without_secret_text(
    code: int,
    expected: type[Exception],
) -> None:
    sdk = MagicMock()
    sdk.models.generate_content.side_effect = errors.ClientError(
        code, {"message": "gemini-test-secret must never escape"}
    )

    with pytest.raises(expected) as exc_info:
        _client(sdk).generate(_request())

    assert "gemini-test-secret" not in str(exc_info.value)


def test_missing_gemini_key_fails_at_construction() -> None:
    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        GeminiLLMClient(
            api_key="",
            model="model",
            timeout_seconds=30,
            max_retries=2,
            max_output_tokens=100,
        )
