"""Application-factory composition tests."""

from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app


def test_create_app_registers_current_public_api_contracts() -> None:
    application = create_app(Settings(app_name="Test Analytics API", app_env="test"))
    registered_paths = set(application.openapi()["paths"])

    assert isinstance(application, FastAPI)
    assert {
        "/api/health",
        "/api/ui-feature-flags",
        "/api/tool-flags",
        "/api/chat-mode/welcome",
        "/api/knowledge-catalog/query",
        "/chat",
        "/chat/select-mode",
        "/chat/reset",
    }.issubset(registered_paths)
