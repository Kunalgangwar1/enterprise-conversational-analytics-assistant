"""Lazy construction of configured production embedding clients."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.knowledge_catalog.embeddings.azure_openai import AzureOpenAIEmbeddingClient
from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.embeddings.gemini import GeminiEmbeddingClient
from app.knowledge_catalog.exceptions import EmbeddingConfigurationError
from app.reliability.clients import ResilientEmbeddingClient
from app.reliability.factory import build_provider_retry_policy
from app.reliability.resources import register_provider_resource


@lru_cache(maxsize=1)
def get_embedding_client() -> EmbeddingClient:
    """Construct the configured adapter only when vector functionality runs."""

    return create_embedding_client(get_settings())


def create_embedding_client(settings: Settings) -> EmbeddingClient:
    provider = settings.embedding_provider.strip().lower()
    if provider == "gemini":
        key = (
            settings.gemini_api_key.get_secret_value()
            if settings.gemini_api_key is not None
            else ""
        )
        if not key.strip():
            raise EmbeddingConfigurationError("Missing required Gemini setting: GEMINI_API_KEY")
        raw: EmbeddingClient = GeminiEmbeddingClient(
            api_key=key,
            model=settings.gemini_embedding_model,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.llm_timeout_seconds,
            connect_timeout_seconds=settings.llm_connect_timeout_seconds,
            max_retries=0,
        )
    elif provider == "azure_openai":
        raw = _create_azure_client(settings)
    else:
        raise EmbeddingConfigurationError(
            f"Unsupported embedding provider: {settings.embedding_provider}"
        )
    return register_provider_resource(
        ResilientEmbeddingClient(
            raw,
            provider=provider,
            policy=build_provider_retry_policy(settings),
        )
    )


def _create_azure_client(settings: Settings) -> EmbeddingClient:
    missing: list[str] = []
    if not settings.azure_openai_endpoint or not settings.azure_openai_endpoint.strip():
        missing.append("AZURE_OPENAI_ENDPOINT")
    key = (
        settings.azure_openai_api_key.get_secret_value()
        if settings.azure_openai_api_key is not None
        else ""
    )
    if not key.strip():
        missing.append("AZURE_OPENAI_API_KEY")
    deployment = settings.azure_openai_embedding_deployment or ""
    if not deployment.strip():
        missing.append("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    if missing:
        raise EmbeddingConfigurationError(
            "Missing required Azure OpenAI embedding settings: " + ", ".join(missing)
        )
    return AzureOpenAIEmbeddingClient(
        endpoint=settings.azure_openai_endpoint or "",
        api_key=key,
        deployment=deployment,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.llm_timeout_seconds,
        connect_timeout_seconds=settings.llm_connect_timeout_seconds,
        max_retries=0,
    )
