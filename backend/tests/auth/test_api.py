"""FastAPI 401/403/current-principal boundary tests."""

from fastapi.testclient import TestClient

from app.auth.roles import AppRole
from app.core.config import Settings
from app.main import create_app
from tests.auth.helpers import FixedAuthenticationBackend, principal


def _client(backend: FixedAuthenticationBackend) -> TestClient:
    return TestClient(
        create_app(
            Settings(_env_file=None, app_env="test"),
            authentication_backend=backend,
        )
    )


def test_health_remains_public_but_application_endpoint_requires_authentication() -> None:
    with _client(FixedAuthenticationBackend(None)) as client:
        health = client.get("/api/health")
        protected = client.get("/api/chat-mode/welcome", params={"mode": "auto"})

    assert health.status_code == 200
    assert protected.status_code == 401
    assert protected.json()["error"] == {
        "code": "authentication_required",
        "message": "Authentication is required.",
    }


def test_authenticated_principal_without_permission_receives_403() -> None:
    with _client(FixedAuthenticationBackend(principal(None))) as client:
        response = client.get("/api/dashboards/overview")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_viewer_cannot_bypass_sql_execution_with_direct_api_call() -> None:
    with _client(FixedAuthenticationBackend(principal(AppRole.VIEWER))) as client:
        response = client.post("/chat/execute-sql", headers={"X-Tab-Id": "viewer-tab"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_auth_me_returns_only_safe_normalized_identity() -> None:
    with _client(FixedAuthenticationBackend(principal(AppRole.VIEWER))) as client:
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer never-return-this", "X-Admin": "true"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "synthetic-user"
    assert body["roles"] == ["viewer"]
    assert "dashboard.read" in body["permissions"]
    assert "raw_jwt" not in body
    assert "token" not in response.text.lower()


def test_development_auth_ignores_user_controlled_identity_headers() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            auth_dev_subject="configured-developer",
            auth_dev_roles="viewer",
        )
    )
    with TestClient(application) as client:
        response = client.get(
            "/api/auth/me",
            headers={"X-User": "attacker", "X-Role": "admin", "X-Admin": "true"},
        )
    assert response.status_code == 200
    assert response.json()["subject"] == "configured-developer"
    assert response.json()["roles"] == ["viewer"]
