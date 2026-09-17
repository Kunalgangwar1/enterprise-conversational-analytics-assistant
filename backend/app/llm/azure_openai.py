"""Azure OpenAI adapter using the official SDK Responses API."""

from collections.abc import Callable
from time import perf_counter
from typing import NoReturn
from urllib.parse import urlsplit, urlunsplit

import httpx
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)
from pydantic import ValidationError

from app.llm.base import StructuredModel
from app.llm.exceptions import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequestError,
    LLMStructuredOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm.models import LLMProvider, LLMRequest, LLMResponse, LLMUsage
from app.reliability.errors import retry_after_from_exception


class AzureOpenAILLMClient:
    """Translate provider-neutral requests to Azure's OpenAI-compatible v1 API."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        timeout_seconds: float,
        max_retries: int,
        max_output_tokens: int,
        connect_timeout_seconds: float = 5.0,
        sdk_client: OpenAI | None = None,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError("AZURE_OPENAI_API_KEY must not be blank")
        if not deployment.strip():
            raise LLMConfigurationError("AZURE_OPENAI_DEPLOYMENT must not be blank")
        if timeout_seconds <= 0:
            raise LLMConfigurationError("LLM_TIMEOUT_SECONDS must be greater than zero")
        if max_retries < 0:
            raise LLMConfigurationError("LLM_MAX_RETRIES cannot be negative")
        if max_output_tokens < 1:
            raise LLMConfigurationError("LLM_MAX_OUTPUT_TOKENS must be at least one")
        if connect_timeout_seconds <= 0 or connect_timeout_seconds > timeout_seconds:
            raise LLMConfigurationError(
                "LLM_CONNECT_TIMEOUT_SECONDS must be positive and not exceed the request timeout"
            )

        self._provider = LLMProvider.AZURE_OPENAI
        self._deployment = deployment.strip()
        self._max_output_tokens = max_output_tokens
        self._timer = timer
        self._client = sdk_client or OpenAI(
            api_key=api_key,
            base_url=normalize_azure_openai_base_url(endpoint),
            timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
            max_retries=0,
        )

    def close(self) -> None:
        self._client.close()

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text with the Responses API and return safe typed metadata."""

        started_at = self._timer()
        try:
            response = self._client.responses.create(**self._request_parameters(request))
        except OpenAIError as exc:
            _raise_translated_provider_error(exc)
        elapsed_ms = (self._timer() - started_at) * 1_000

        output_text = response.output_text
        if not output_text or not output_text.strip():
            raise LLMProviderError("LLM provider returned an empty text response")

        return LLMResponse(
            text=output_text,
            provider=self._provider,
            model=self._deployment,
            request_id=getattr(response, "id", None),
            usage=_map_usage(getattr(response, "usage", None)),
            elapsed_ms=elapsed_ms,
        )

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        """Use SDK-native Responses parsing and return a validated Pydantic model."""

        try:
            response = self._client.responses.parse(
                **self._request_parameters(request),
                text_format=response_model,
            )
        except OpenAIError as exc:
            _raise_translated_provider_error(exc)
        except ValidationError as exc:
            raise LLMStructuredOutputError(
                "LLM provider returned invalid structured output"
            ) from exc

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise LLMStructuredOutputError("LLM provider did not return parsed structured output")
        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise LLMStructuredOutputError(
                "LLM provider returned invalid structured output"
            ) from exc

    def _request_parameters(self, request: LLMRequest) -> dict[str, object]:
        parameters: dict[str, object] = {
            "model": self._deployment,
            "input": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "max_output_tokens": request.max_output_tokens or self._max_output_tokens,
        }
        if request.temperature is not None:
            parameters["temperature"] = request.temperature
        return parameters


def normalize_azure_openai_base_url(endpoint: str) -> str:
    """Normalize a resource endpoint to one Azure OpenAI v1 base URL."""

    raw_endpoint = endpoint.strip()
    parsed = urlsplit(raw_endpoint)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LLMConfigurationError(
            "AZURE_OPENAI_ENDPOINT must be an HTTPS resource endpoint without credentials, "
            "query parameters, or fragments"
        )

    segments = [segment for segment in parsed.path.split("/") if segment]
    while [segment.lower() for segment in segments[-4:]] == [
        "openai",
        "v1",
        "openai",
        "v1",
    ]:
        segments = segments[:-2]
    if [segment.lower() for segment in segments[-2:]] != ["openai", "v1"]:
        segments.extend(("openai", "v1"))

    normalized_path = f"/{'/'.join(segments)}/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, normalized_path, "", ""))


def _map_usage(provider_usage: object | None) -> LLMUsage:
    if provider_usage is None:
        return LLMUsage()
    return LLMUsage(
        input_tokens=_optional_nonnegative_int(provider_usage, "input_tokens"),
        output_tokens=_optional_nonnegative_int(provider_usage, "output_tokens"),
        total_tokens=_optional_nonnegative_int(provider_usage, "total_tokens"),
    )


def _optional_nonnegative_int(value: object, attribute: str) -> int | None:
    candidate = getattr(value, attribute, None)
    return candidate if isinstance(candidate, int) and candidate >= 0 else None


def _raise_translated_provider_error(exc: OpenAIError) -> NoReturn:
    if isinstance(exc, APITimeoutError):
        raise LLMTimeoutError("LLM provider request timed out") from exc
    if isinstance(exc, AuthenticationError):
        raise LLMAuthenticationError("LLM provider authentication failed") from exc
    if isinstance(exc, RateLimitError):
        raise LLMRateLimitError(
            "LLM provider rate limit was exceeded",
            retry_after_seconds=retry_after_from_exception(exc),
        ) from exc
    if isinstance(exc, APIConnectionError):
        raise LLMUnavailableError("LLM provider is unavailable") from exc
    if isinstance(exc, APIStatusError):
        if exc.status_code == 408:
            raise LLMTimeoutError("LLM provider request timed out") from exc
        if exc.status_code in {500, 502, 503, 504}:
            raise LLMUnavailableError("LLM provider is unavailable") from exc
        if 400 <= exc.status_code < 500:
            raise LLMRequestError("LLM provider rejected the request") from exc
    if isinstance(exc, APIError):
        raise LLMProviderError("LLM provider request failed") from exc
    raise LLMProviderError("Unexpected LLM provider failure") from exc
