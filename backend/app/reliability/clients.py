"""Provider-neutral reliability decorators for LLM and embedding reads."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.llm.base import LLMClient, StructuredModel
from app.llm.models import LLMRequest, LLMResponse
from app.observability.metrics import get_metrics
from app.reliability.errors import (
    CircuitOpenError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.reliability.policy import RetryPolicy

if TYPE_CHECKING:
    from app.knowledge_catalog.embeddings.base import EmbeddingClient

_FALLBACK_ERRORS = (
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    CircuitOpenError,
)


class ResilientLLMClient:
    """Retry only side-effect-free generation calls under a fixed policy budget."""

    def __init__(self, client: LLMClient, *, provider: str, policy: RetryPolicy) -> None:
        self._client = client
        self._provider = provider
        self._policy = policy
        self._closed = False

    def generate(self, request: LLMRequest) -> LLMResponse:
        return self._policy.execute(
            lambda: self._client.generate(request),
            provider=self._provider,
            operation="generate",
        )

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        return self._policy.execute(
            lambda: self._client.generate_structured(request, response_model),
            provider=self._provider,
            operation="generate_structured",
        )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            _close_if_supported(self._client)


class FallbackLLMClient:
    """Use one explicitly configured secondary provider for transient primary failures."""

    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient,
        *,
        fallback_provider: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_provider = fallback_provider
        self._closed = False

    def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            return self._primary.generate(request)
        except _FALLBACK_ERRORS as exc:
            self._record("generate", exc)
            return self._fallback.generate(request)

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        try:
            return self._primary.generate_structured(request, response_model)
        except _FALLBACK_ERRORS as exc:
            self._record("generate_structured", exc)
            return self._fallback.generate_structured(request, response_model)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            _close_if_supported(self._primary)
            _close_if_supported(self._fallback)

    def _record(self, operation: str, error: Exception) -> None:
        get_metrics().record(
            "provider.fallbacks",
            1,
            {
                "provider": self._fallback_provider,
                "operation": operation,
                "reason_code": _reason_code(error),
            },
        )


class ResilientEmbeddingClient:
    """Apply the same bounded reliability policy to read-only embedding operations."""

    def __init__(self, client: EmbeddingClient, *, provider: str, policy: RetryPolicy) -> None:
        self._client = client
        self._provider = provider
        self._policy = policy
        self._closed = False

    @property
    def provider_name(self) -> str:
        return self._client.provider_name

    @property
    def model_name(self) -> str:
        return self._client.model_name

    @property
    def dimensions(self) -> int | None:
        return self._client.dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._policy.execute(
            lambda: self._client.embed_documents(texts),
            provider=self._provider,
            operation="embed_documents",
        )

    def embed_query(self, text: str) -> list[float]:
        return self._policy.execute(
            lambda: self._client.embed_query(text),
            provider=self._provider,
            operation="embed_query",
        )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            _close_if_supported(self._client)


def _close_if_supported(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _reason_code(error: Exception) -> str:
    if isinstance(error, CircuitOpenError):
        return "circuit_open"
    if isinstance(error, ProviderTimeoutError):
        return "timeout"
    if isinstance(error, ProviderRateLimitError):
        return "rate_limited"
    return "unavailable"
