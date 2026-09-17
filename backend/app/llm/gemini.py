"""Gemini adapter implementing the provider-neutral LLM contract."""

from collections.abc import Callable
from time import perf_counter
from typing import Any, NoReturn

import httpx
from google import genai
from google.genai import errors, types
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
from app.llm.models import LLMProvider, LLMRequest, LLMResponse, LLMRole, LLMUsage
from app.reliability.errors import retry_after_from_exception


class GeminiLLMClient:
    """Map existing LLM requests to the official Google Gen AI SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        max_output_tokens: int,
        connect_timeout_seconds: float = 5.0,
        sdk_client: Any | None = None,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        if not api_key.strip():
            raise LLMConfigurationError("GEMINI_API_KEY must not be blank")
        if not model.strip():
            raise LLMConfigurationError("GEMINI_LLM_MODEL must not be blank")
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

        self._model = model.strip()
        self._max_output_tokens = max_output_tokens
        self._timer = timer
        self._client = sdk_client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1_000),
                client_args={
                    "timeout": httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds)
                },
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def generate(self, request: LLMRequest) -> LLMResponse:
        started_at = self._timer()
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=_gemini_contents(request),
                config=self._config(request),
            )
            output_text = response.text
        except (errors.APIError, httpx.TransportError, TimeoutError) as exc:
            _raise_translated_gemini_error(exc)
        except (ValueError, AttributeError) as exc:
            raise LLMProviderError("Gemini returned an invalid text response") from exc
        if not output_text or not output_text.strip():
            raise LLMProviderError("LLM provider returned an empty text response")
        return LLMResponse(
            text=output_text,
            provider=LLMProvider.GEMINI,
            model=self._model,
            request_id=getattr(response, "response_id", None),
            usage=_map_usage(getattr(response, "usage_metadata", None)),
            elapsed_ms=(self._timer() - started_at) * 1_000,
        )

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=_gemini_contents(request),
                config=self._config(request, response_model=response_model),
            )
        except (errors.APIError, httpx.TransportError, TimeoutError) as exc:
            _raise_translated_gemini_error(exc)
        parsed = getattr(response, "parsed", None)
        if parsed is None:
            raise LLMStructuredOutputError("LLM provider did not return parsed structured output")
        try:
            return response_model.model_validate(parsed)
        except (ValidationError, TypeError, ValueError) as exc:
            raise LLMStructuredOutputError(
                "LLM provider returned invalid structured output"
            ) from exc

    def _config(
        self,
        request: LLMRequest,
        *,
        response_model: type[StructuredModel] | None = None,
    ) -> types.GenerateContentConfig:
        system_instruction = "\n\n".join(
            message.content for message in request.messages if message.role == LLMRole.SYSTEM
        )
        values: dict[str, object] = {
            "max_output_tokens": request.max_output_tokens or self._max_output_tokens,
        }
        if system_instruction:
            values["system_instruction"] = system_instruction
        if response_model is not None:
            values["response_mime_type"] = "application/json"
            values["response_schema"] = response_model
        return types.GenerateContentConfig(**values)


def _gemini_contents(request: LLMRequest) -> list[types.Content]:
    contents = [
        types.Content(
            role="model" if message.role == LLMRole.ASSISTANT else "user",
            parts=[types.Part.from_text(text=message.content)],
        )
        for message in request.messages
        if message.role != LLMRole.SYSTEM
    ]
    if not contents:
        raise LLMConfigurationError("Gemini requests require at least one non-system message")
    return contents


def _map_usage(usage: object | None) -> LLMUsage:
    if usage is None:
        return LLMUsage()
    return LLMUsage(
        input_tokens=_nonnegative_int(usage, "prompt_token_count"),
        output_tokens=_nonnegative_int(usage, "candidates_token_count"),
        total_tokens=_nonnegative_int(usage, "total_token_count"),
    )


def _nonnegative_int(value: object, attribute: str) -> int | None:
    candidate = getattr(value, attribute, None)
    return candidate if isinstance(candidate, int) and candidate >= 0 else None


def _raise_translated_gemini_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        raise LLMTimeoutError("LLM provider request timed out") from exc
    if isinstance(exc, httpx.TransportError):
        raise LLMUnavailableError("LLM provider is unavailable") from exc
    code = getattr(exc, "code", None)
    if code in {401, 403}:
        raise LLMAuthenticationError("LLM provider authentication failed") from exc
    if code == 429:
        raise LLMRateLimitError(
            "LLM provider rate limit was exceeded",
            retry_after_seconds=retry_after_from_exception(exc),
        ) from exc
    if code in {408, 504}:
        raise LLMTimeoutError("LLM provider request timed out") from exc
    if code in {500, 502, 503}:
        raise LLMUnavailableError("LLM provider is unavailable") from exc
    if isinstance(code, int) and 400 <= code < 500:
        raise LLMRequestError("LLM provider rejected the request") from exc
    raise LLMProviderError("LLM provider request failed") from exc
