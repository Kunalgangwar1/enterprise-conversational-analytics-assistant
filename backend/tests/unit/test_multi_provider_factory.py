"""Configuration-only LLM provider selection tests."""

from unittest.mock import MagicMock

import pytest

import app.llm.factory as factory
from app.core.config import Settings
from app.llm.exceptions import LLMConfigurationError


def test_gemini_is_default_and_selected_through_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(factory, "GeminiLLMClient", constructor)
    settings = Settings(_env_file=None, gemini_api_key="test-key")

    factory.create_llm_client(settings)

    constructor.assert_called_once()
    assert constructor.call_args.kwargs["model"] == "gemini-3.8-flash"


def test_azure_remains_selectable_through_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(factory, "AzureOpenAILLMClient", constructor)
    settings = Settings(
        _env_file=None,
        llm_provider="azure_openai",
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_api_key="test-key",
        azure_openai_deployment="deployment",
    )

    factory.create_llm_client(settings)

    constructor.assert_called_once()


def test_missing_gemini_key_and_unknown_provider_fail_clearly() -> None:
    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        factory.create_llm_client(Settings(_env_file=None))
    with pytest.raises(LLMConfigurationError, match="Unsupported LLM provider"):
        factory.create_llm_client(Settings(_env_file=None, llm_provider="unknown"))
