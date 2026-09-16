"""Unit tests for provider-neutral LLM models and settings."""

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.main import create_app


def test_llm_message_accepts_supported_roles_and_meaningful_content() -> None:
    message = LLMMessage(role=LLMRole.USER, content="  Explain this concept.  ")

    assert message.role is LLMRole.USER
    assert message.content == "Explain this concept."


def test_llm_message_rejects_unknown_role_and_blank_content() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role="tool", content="result")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LLMMessage(role=LLMRole.USER, content="   ")


def test_llm_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        LLMRequest(messages=[])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_timeout_seconds", 0),
        ("llm_timeout_seconds", -1),
        ("llm_max_retries", -1),
        ("llm_max_output_tokens", 0),
    ],
)
def test_invalid_llm_settings_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})  # type: ignore[call-arg]


def test_fastapi_factory_does_not_require_azure_credentials() -> None:
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint=None,
        azure_openai_api_key=None,
        azure_openai_deployment=None,
    )

    application = create_app(settings)

    assert isinstance(application, FastAPI)
