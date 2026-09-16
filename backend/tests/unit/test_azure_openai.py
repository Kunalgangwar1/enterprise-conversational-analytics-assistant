"""Network-free unit tests for the Azure OpenAI provider adapter."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIError, APITimeoutError, AuthenticationError, RateLimitError
from pydantic import BaseModel

import app.llm.azure_openai as azure_openai_module
from app.llm.azure_openai import AzureOpenAILLMClient, normalize_azure_openai_base_url
from app.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from app.llm.models import LLMMessage, LLMRequest, LLMRole


class StructuredAnswer(BaseModel):
    answer: str


def _request(*, temperature: float | None = None) -> LLMRequest:
    return LLMRequest(
        messages=[
            LLMMessage(role=LLMRole.SYSTEM, content="Return a concise answer."),
            LLMMessage(role=LLMRole.USER, content="Harmless test prompt"),
        ],
        temperature=temperature,
    )


def _client(
    sdk_client: MagicMock,
    *,
    timer: MagicMock | None = None,
) -> AzureOpenAILLMClient:
    return AzureOpenAILLMClient(
        endpoint="https://example.openai.azure.com/",
        api_key="test-key",
        deployment="test-deployment",
        timeout_seconds=30,
        max_retries=2,
        max_output_tokens=2_000,
        sdk_client=sdk_client,
        timer=timer or MagicMock(side_effect=[1.0, 1.1]),
    )


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        (
            "https://example.openai.azure.com/",
            "https://example.openai.azure.com/openai/v1/",
        ),
        (
            "https://example.openai.azure.com/openai/v1/",
            "https://example.openai.azure.com/openai/v1/",
        ),
        (
            "https://example.openai.azure.com//openai/v1/openai/v1//",
            "https://example.openai.azure.com/openai/v1/",
        ),
    ],
)
def test_azure_endpoint_normalization(endpoint: str, expected: str) -> None:
    assert normalize_azure_openai_base_url(endpoint) == expected


def test_azure_endpoint_rejects_unsafe_or_invalid_values() -> None:
    with pytest.raises(LLMConfigurationError):
        normalize_azure_openai_base_url("http://example.openai.azure.com/?key=secret")


def test_adapter_configures_official_sdk_timeout_retries_and_v1_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_constructor = MagicMock()
    monkeypatch.setattr(azure_openai_module, "OpenAI", sdk_constructor)

    AzureOpenAILLMClient(
        endpoint="https://example.openai.azure.com/",
        api_key="test-key",
        deployment="test-deployment",
        timeout_seconds=12.5,
        max_retries=4,
        max_output_tokens=800,
    )

    sdk_constructor.assert_called_once_with(
        api_key="test-key",
        base_url="https://example.openai.azure.com/openai/v1/",
        timeout=12.5,
        max_retries=4,
    )


def test_text_request_maps_messages_response_usage_and_optional_parameters() -> None:
    sdk_client = MagicMock()
    sdk_client.responses.create.return_value = SimpleNamespace(
        output_text="Provider response",
        id="response-123",
        usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
    )
    timer = MagicMock(side_effect=[10.0, 10.125])

    response = _client(sdk_client, timer=timer).generate(_request())

    assert response.text == "Provider response"
    assert response.provider == "azure_openai"
    assert response.model == "test-deployment"
    assert response.request_id == "response-123"
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 18
    assert response.elapsed_ms == 125
    parameters = sdk_client.responses.create.call_args.kwargs
    assert parameters["model"] == "test-deployment"
    assert parameters["input"] == [
        {"role": "system", "content": "Return a concise answer."},
        {"role": "user", "content": "Harmless test prompt"},
    ]
    assert parameters["max_output_tokens"] == 2_000
    assert "temperature" not in parameters


def test_explicit_temperature_and_max_tokens_are_forwarded() -> None:
    sdk_client = MagicMock()
    sdk_client.responses.create.return_value = SimpleNamespace(
        output_text="OK",
        id=None,
        usage=None,
    )
    request = _request(temperature=0.2).model_copy(update={"max_output_tokens": 100})

    _client(sdk_client).generate(request)

    parameters = sdk_client.responses.create.call_args.kwargs
    assert parameters["temperature"] == 0.2
    assert parameters["max_output_tokens"] == 100


def test_empty_text_response_is_a_controlled_provider_error() -> None:
    sdk_client = MagicMock()
    sdk_client.responses.create.return_value = SimpleNamespace(
        output_text="  ",
        id="response-empty",
        usage=None,
    )

    with pytest.raises(LLMProviderError, match="empty text"):
        _client(sdk_client).generate(_request())


def _sdk_exception(kind: str) -> Exception:
    request = httpx.Request("POST", "https://example.invalid/openai/v1/responses")
    if kind == "timeout":
        return APITimeoutError(request=request)
    if kind == "authentication":
        response = httpx.Response(401, request=request)
        return AuthenticationError("unauthorized", response=response, body=None)
    if kind == "rate_limit":
        response = httpx.Response(429, request=request)
        return RateLimitError("limited", response=response, body=None)
    return APIError("provider failed", request=request, body=None)


@pytest.mark.parametrize(
    ("sdk_error", "expected_error"),
    [
        (_sdk_exception("timeout"), LLMTimeoutError),
        (_sdk_exception("authentication"), LLMAuthenticationError),
        (_sdk_exception("rate_limit"), LLMRateLimitError),
        (_sdk_exception("generic"), LLMProviderError),
    ],
)
def test_sdk_exceptions_are_translated(
    sdk_error: Exception,
    expected_error: type[Exception],
) -> None:
    sdk_client = MagicMock()
    sdk_client.responses.create.side_effect = sdk_error

    with pytest.raises(expected_error):
        _client(sdk_client).generate(_request())


def test_structured_output_uses_sdk_parser_and_returns_validated_model() -> None:
    sdk_client = MagicMock()
    sdk_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=StructuredAnswer(answer="validated")
    )

    result = _client(sdk_client).generate_structured(_request(), StructuredAnswer)

    assert result == StructuredAnswer(answer="validated")
    parameters = sdk_client.responses.parse.call_args.kwargs
    assert parameters["text_format"] is StructuredAnswer
    assert parameters["input"][1]["content"] == "Harmless test prompt"


@pytest.mark.parametrize(
    "parsed_output",
    [None, {"wrong_field": "invalid"}],
)
def test_missing_or_invalid_structured_output_raises_controlled_error(
    parsed_output: object,
) -> None:
    sdk_client = MagicMock()
    sdk_client.responses.parse.return_value = SimpleNamespace(output_parsed=parsed_output)

    with pytest.raises(LLMStructuredOutputError):
        _client(sdk_client).generate_structured(_request(), StructuredAnswer)
