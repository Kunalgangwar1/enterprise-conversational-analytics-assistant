"""API tests for canonical chat-mode welcome responses."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(
        create_app(Settings(app_name="Test Analytics API", app_env="test"))
    ) as test_client:
        yield test_client


@pytest.mark.parametrize("mode", ["auto", "sql", "data_quality"])
def test_welcome_endpoint_returns_configured_mode(
    client: TestClient,
    mode: str,
) -> None:
    response = client.get("/api/chat-mode/welcome", params={"mode": mode})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == mode
    assert payload["display_name"]
    assert payload["description"]
    assert payload["welcome_message"]


def test_unsupported_mode_uses_standard_error_envelope(client: TestClient) -> None:
    response = client.get(
        "/api/chat-mode/welcome",
        params={"mode": "magic_ai"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_chat_mode",
            "message": "Unsupported chat mode: magic_ai",
        }
    }
