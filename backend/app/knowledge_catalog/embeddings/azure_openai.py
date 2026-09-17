"""Azure OpenAI implementation of the embedding contract."""

from typing import NoReturn

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

from app.knowledge_catalog.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingRequestError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
)
from app.llm.azure_openai import normalize_azure_openai_base_url
from app.reliability.errors import retry_after_from_exception


class AzureOpenAIEmbeddingClient:
    """Use the official SDK without exposing provider objects to callers."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        dimensions: int | None = None,
        timeout_seconds: float = 30,
        max_retries: int = 2,
        connect_timeout_seconds: float = 5.0,
        sdk_client: OpenAI | None = None,
    ) -> None:
        if not api_key.strip():
            raise EmbeddingConfigurationError("AZURE_OPENAI_API_KEY must not be blank")
        if not deployment.strip():
            raise EmbeddingConfigurationError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT must not be blank")
        if dimensions is not None and dimensions < 1:
            raise EmbeddingConfigurationError("EMBEDDING_DIMENSIONS must be positive")
        if timeout_seconds <= 0:
            raise EmbeddingConfigurationError("LLM_TIMEOUT_SECONDS must be greater than zero")
        if max_retries < 0:
            raise EmbeddingConfigurationError("LLM_MAX_RETRIES cannot be negative")
        if connect_timeout_seconds <= 0 or connect_timeout_seconds > timeout_seconds:
            raise EmbeddingConfigurationError(
                "LLM_CONNECT_TIMEOUT_SECONDS must be positive and not exceed the request timeout"
            )
        self._deployment = deployment.strip()
        self._dimensions = dimensions
        self._client = sdk_client or OpenAI(
            api_key=api_key,
            base_url=normalize_azure_openai_base_url(endpoint),
            timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
            max_retries=0,
        )

    def close(self) -> None:
        self._client.close()

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    @property
    def model_name(self) -> str:
        return self._deployment

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingProviderError("Embedding query must not be blank")
        return self._embed([text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        parameters: dict[str, object] = {"model": self._deployment, "input": texts}
        if self._dimensions is not None:
            parameters["dimensions"] = self._dimensions
        try:
            response = self._client.embeddings.create(**parameters)
        except OpenAIError as exc:
            _raise_translated_embedding_error(exc)
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise EmbeddingProviderError("Embedding provider returned an invalid batch")
        return vectors


def _raise_translated_embedding_error(exc: OpenAIError) -> NoReturn:
    if isinstance(exc, APITimeoutError):
        raise EmbeddingTimeoutError("Embedding provider request timed out") from exc
    if isinstance(exc, AuthenticationError):
        raise EmbeddingAuthenticationError("Embedding provider authentication failed") from exc
    if isinstance(exc, RateLimitError):
        raise EmbeddingRateLimitError(
            "Embedding provider rate limit was exceeded",
            retry_after_seconds=retry_after_from_exception(exc),
        ) from exc
    if isinstance(exc, APIConnectionError):
        raise EmbeddingUnavailableError("Embedding provider is unavailable") from exc
    if isinstance(exc, APIStatusError):
        if exc.status_code == 408:
            raise EmbeddingTimeoutError("Embedding provider request timed out") from exc
        if exc.status_code in {500, 502, 503, 504}:
            raise EmbeddingUnavailableError("Embedding provider is unavailable") from exc
        if 400 <= exc.status_code < 500:
            raise EmbeddingRequestError("Embedding provider rejected the request") from exc
    if isinstance(exc, APIError):
        raise EmbeddingProviderError("Embedding provider request failed") from exc
    raise EmbeddingProviderError("Unexpected embedding provider failure") from exc
