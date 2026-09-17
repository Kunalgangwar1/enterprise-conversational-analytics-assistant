"""Lazy construction of configured production LLM clients."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.llm.azure_openai import AzureOpenAILLMClient
from app.llm.base import LLMClient
from app.llm.exceptions import LLMConfigurationError
from app.llm.gemini import GeminiLLMClient
from app.observability.llm import InstrumentedLLMClient


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Construct and cache the configured provider only when first requested."""

    return create_llm_client(get_settings())


def create_llm_client(settings: Settings) -> LLMClient:
    """Validate provider configuration and construct one real adapter."""

    provider = settings.llm_provider.strip().lower()
    if provider == "gemini":
        key = (
            settings.gemini_api_key.get_secret_value()
            if settings.gemini_api_key is not None
            else ""
        )
        if not key.strip():
            raise LLMConfigurationError("Missing required Gemini setting: GEMINI_API_KEY")
        client = GeminiLLMClient(
            api_key=key,
            model=settings.gemini_llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            max_output_tokens=settings.llm_max_output_tokens,
        )
        if settings.observability_enabled:
            return InstrumentedLLMClient(
                client,
                provider="gemini",
                model=settings.gemini_llm_model,
            )
        return client
    if provider != "azure_openai":
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")

    missing_settings: list[str] = []
    if not settings.azure_openai_endpoint or not settings.azure_openai_endpoint.strip():
        missing_settings.append("AZURE_OPENAI_ENDPOINT")
    api_key = (
        settings.azure_openai_api_key.get_secret_value()
        if settings.azure_openai_api_key is not None
        else ""
    )
    if not api_key.strip():
        missing_settings.append("AZURE_OPENAI_API_KEY")
    if not settings.azure_openai_deployment or not settings.azure_openai_deployment.strip():
        missing_settings.append("AZURE_OPENAI_DEPLOYMENT")
    if missing_settings:
        raise LLMConfigurationError(
            "Missing required Azure OpenAI settings: " + ", ".join(missing_settings)
        )

    client = AzureOpenAILLMClient(
        endpoint=settings.azure_openai_endpoint,
        api_key=api_key,
        deployment=settings.azure_openai_deployment,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_output_tokens=settings.llm_max_output_tokens,
    )
    if settings.observability_enabled:
        return InstrumentedLLMClient(
            client,
            provider="azure_openai",
            model=settings.azure_openai_deployment,
        )
    return client
