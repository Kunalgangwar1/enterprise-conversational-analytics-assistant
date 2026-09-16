"""Unit tests for lazy configured LLM construction."""

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

import app.llm.factory as factory_module
from app.core.config import Settings
from app.llm.exceptions import LLMConfigurationError


@pytest.fixture(autouse=True)
def clear_llm_client_cache() -> Iterator[None]:
    factory_module.get_llm_client.cache_clear()
    yield
    factory_module.get_llm_client.cache_clear()


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_provider": "azure_openai",
        "azure_openai_endpoint": "https://example.openai.azure.com/",
        "azure_openai_api_key": "test-key",
        "azure_openai_deployment": "test-deployment",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_factory_requires_complete_azure_configuration() -> None:
    settings = _settings(
        azure_openai_endpoint=None,
        azure_openai_api_key=None,
        azure_openai_deployment=None,
    )

    with pytest.raises(LLMConfigurationError, match="AZURE_OPENAI_ENDPOINT") as exc_info:
        factory_module.create_llm_client(settings)

    assert "AZURE_OPENAI_API_KEY" in str(exc_info.value)
    assert "AZURE_OPENAI_DEPLOYMENT" in str(exc_info.value)


def test_get_llm_client_reports_missing_configuration_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_settings = _settings(
        azure_openai_endpoint=None,
        azure_openai_api_key=None,
        azure_openai_deployment=None,
    )
    monkeypatch.setattr(factory_module, "get_settings", lambda: missing_settings)

    with pytest.raises(LLMConfigurationError, match="Missing required Azure OpenAI settings"):
        factory_module.get_llm_client()


def test_factory_rejects_unsupported_provider_without_fallback() -> None:
    with pytest.raises(LLMConfigurationError, match="Unsupported LLM provider"):
        factory_module.create_llm_client(_settings(llm_provider="anthropic"))


def test_get_llm_client_constructs_lazily_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    configured_settings = _settings()
    constructed_client = MagicMock(name="configured_llm_client")
    constructor = MagicMock(return_value=constructed_client)
    monkeypatch.setattr(factory_module, "get_settings", lambda: configured_settings)
    monkeypatch.setattr(factory_module, "AzureOpenAILLMClient", constructor)

    first = factory_module.get_llm_client()
    second = factory_module.get_llm_client()

    assert first is constructed_client
    assert second is constructed_client
    constructor.assert_called_once()
