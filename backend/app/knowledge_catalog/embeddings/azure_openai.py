"""Azure OpenAI implementation of the embedding contract."""

from typing import NoReturn

from openai import (
    APIError,
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
    EmbeddingTimeoutError,
)
from app.llm.azure_openai import normalize_azure_openai_base_url


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
        sdk_client: OpenAI | None = None,
    ) -> None:
        if not api_key.strip():
            raise EmbeddingConfigurationError("AZURE_OPENAI_API_KEY must not be blank")
        if not deployment.strip():
            raise EmbeddingConfigurationError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT must not be blank")
        if dimensions is not None and dimensions < 1:
            raise EmbeddingConfigurationError("EMBEDDING_DIMENSIONS must be positive")
        self._deployment = deployment.strip()
        self._dimensions = dimensions
        self._client = sdk_client or OpenAI(
            api_key=api_key,
            base_url=normalize_azure_openai_base_url(endpoint),
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

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
        raise EmbeddingRateLimitError("Embedding provider rate limit was exceeded") from exc
    if isinstance(exc, APIError):
        raise EmbeddingProviderError("Embedding provider request failed") from exc
    raise EmbeddingProviderError("Unexpected embedding provider failure") from exc
