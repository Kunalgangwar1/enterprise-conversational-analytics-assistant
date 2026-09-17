"""Lazy construction of configured, resilient production LLM clients."""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.llm.azure_openai import AzureOpenAILLMClient
from app.llm.base import LLMClient
from app.llm.exceptions import LLMConfigurationError
from app.llm.gemini import GeminiLLMClient
from app.observability.llm import InstrumentedLLMClient
from app.reliability.clients import FallbackLLMClient, ResilientLLMClient
from app.reliability.factory import build_provider_retry_policy
from app.reliability.resources import register_provider_resource


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Construct and cache the configured provider only when first requested."""

    return create_llm_client(get_settings())


def create_llm_client(settings: Settings) -> LLMClient:
    """Validate providers and build bounded resilience with optional explicit fallback."""

    primary_provider = settings.llm_provider.strip().lower()
    primary = _create_provider_client(settings, primary_provider)
    fallback_provider = settings.llm_fallback_provider
    if fallback_provider == "none":
        return register_provider_resource(primary)
    if fallback_provider == primary_provider:
        primary.close()
        raise LLMConfigurationError("LLM_FALLBACK_PROVIDER must differ from LLM_PROVIDER")
    try:
        fallback = _create_provider_client(settings, fallback_provider)
    except Exception:
        primary.close()
        raise
    return register_provider_resource(
        FallbackLLMClient(primary, fallback, fallback_provider=fallback_provider)
    )


def _create_provider_client(settings: Settings, provider: str) -> LLMClient:
    if provider == "gemini":
        key = (
            settings.gemini_api_key.get_secret_value()
            if settings.gemini_api_key is not None
            else ""
        )
        if not key.strip():
            raise LLMConfigurationError("Missing required Gemini setting: GEMINI_API_KEY")
        model = settings.gemini_llm_model
        raw: LLMClient = GeminiLLMClient(
            api_key=key,
            model=model,
            timeout_seconds=settings.llm_timeout_seconds,
            connect_timeout_seconds=settings.llm_connect_timeout_seconds,
            max_retries=0,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    elif provider == "azure_openai":
        endpoint, key, model = _azure_configuration(settings)
        raw = AzureOpenAILLMClient(
            endpoint=endpoint,
            api_key=key,
            deployment=model,
            timeout_seconds=settings.llm_timeout_seconds,
            connect_timeout_seconds=settings.llm_connect_timeout_seconds,
            max_retries=0,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    else:
        raise LLMConfigurationError(f"Unsupported LLM provider: {provider}")

    observed: LLMClient = (
        InstrumentedLLMClient(raw, provider=provider, model=model)
        if settings.observability_enabled
        else raw
    )
    return ResilientLLMClient(
        observed,
        provider=provider,
        policy=build_provider_retry_policy(settings),
    )


def _azure_configuration(settings: Settings) -> tuple[str, str, str]:
    missing: list[str] = []
    endpoint = settings.azure_openai_endpoint or ""
    if not endpoint.strip():
        missing.append("AZURE_OPENAI_ENDPOINT")
    key = (
        settings.azure_openai_api_key.get_secret_value()
        if settings.azure_openai_api_key is not None
        else ""
    )
    if not key.strip():
        missing.append("AZURE_OPENAI_API_KEY")
    deployment = settings.azure_openai_deployment or ""
    if not deployment.strip():
        missing.append("AZURE_OPENAI_DEPLOYMENT")
    if missing:
        raise LLMConfigurationError("Missing required Azure OpenAI settings: " + ", ".join(missing))
    return endpoint, key, deployment
