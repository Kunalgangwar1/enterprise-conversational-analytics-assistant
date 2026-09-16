"""Tests for the service health endpoint."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_endpoint_returns_service_status() -> None:
    test_app = create_app(Settings(app_name="Test Analytics API", app_env="test"))

    with TestClient(test_app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
