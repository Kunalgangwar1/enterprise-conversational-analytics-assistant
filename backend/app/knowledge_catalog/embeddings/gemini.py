"""Gemini implementation of the provider-neutral embedding contract."""

from typing import Any, NoReturn

import httpx
from google import genai
from google.genai import errors, types

from app.knowledge_catalog.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
)


class GeminiEmbeddingClient:
    """Generate retrieval embeddings through the official Google Gen AI SDK."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int | None,
        timeout_seconds: float = 30,
        max_retries: int = 2,
        sdk_client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise EmbeddingConfigurationError("GEMINI_API_KEY must not be blank")
        if not model.strip():
            raise EmbeddingConfigurationError("GEMINI_EMBEDDING_MODEL must not be blank")
        if dimensions is not None and dimensions < 1:
            raise EmbeddingConfigurationError("EMBEDDING_DIMENSIONS must be positive")
        self._model = model.strip()
        self._dimensions = dimensions
        self._client = sdk_client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1_000),
                retry_options=types.HttpRetryOptions(attempts=max_retries + 1),
            ),
        )

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingProviderError("Embedding query must not be blank")
        return self._embed([text], task_type="RETRIEVAL_QUERY")[0]

    def _embed(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        config_values: dict[str, object] = {}
        if self._dimensions is not None:
            config_values["output_dimensionality"] = self._dimensions
        if _supports_retrieval_task_types(self._model):
            config_values["task_type"] = task_type
        try:
            response = self._client.models.embed_content(
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(**config_values),
            )
        except (errors.APIError, httpx.TimeoutException, TimeoutError) as exc:
            _raise_translated_embedding_error(exc)
        embeddings = getattr(response, "embeddings", None)
        vectors = [list(item.values or []) for item in embeddings or []]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise EmbeddingProviderError("Embedding provider returned an invalid batch")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise EmbeddingProviderError("Embedding provider returned inconsistent dimensions")
        if self._dimensions is not None and dimensions != {self._dimensions}:
            raise EmbeddingProviderError("Embedding provider returned unexpected dimensions")
        return vectors


def _supports_retrieval_task_types(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith("gemini-embedding") or normalized.startswith("text-embedding")


def _raise_translated_embedding_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        raise EmbeddingTimeoutError("Embedding provider request timed out") from exc
    code = getattr(exc, "code", None)
    if code in {401, 403}:
        raise EmbeddingAuthenticationError("Embedding provider authentication failed") from exc
    if code == 429:
        raise EmbeddingRateLimitError("Embedding provider rate limit was exceeded") from exc
    if code in {408, 504}:
        raise EmbeddingTimeoutError("Embedding provider request timed out") from exc
    raise EmbeddingProviderError("Embedding provider request failed") from exc
