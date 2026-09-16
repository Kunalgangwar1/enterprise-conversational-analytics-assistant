"""Production configuration and FastAPI network/browser boundary tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.security.production_policy import safe_security_summary


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "artifacts_output_dir": tmp_path,
    }
    values.update(overrides)
    return Settings(**values)


def _production_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "production",
        "auth_mode": "oidc",
        "auth_oidc_issuer": "https://issuer.example.invalid",
        "auth_oidc_jwks_url": "https://issuer.example.invalid/.well-known/jwks.json",
        "session_cookie_secure": True,
        "cors_allowed_origins": ["https://analytics.example.invalid"],
        "allowed_hosts": ["analytics.example.invalid"],
        "api_docs_enabled": False,
        "artifacts_output_dir": tmp_path,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"auth_mode": "development"}, "AUTH_MODE=development"),
        ({"session_cookie_secure": False}, "SESSION_COOKIE_SECURE=false"),
        ({"cors_allowed_origins": ["*"]}, "wildcard CORS"),
        ({"allowed_hosts": []}, "ALLOWED_HOSTS"),
        ({"allowed_hosts": ["*"]}, "ALLOWED_HOSTS"),
        ({"api_docs_enabled": True}, "API_DOCS_ENABLED=true"),
        ({"rate_limit_enabled": False}, "RATE_LIMIT_ENABLED=false"),
    ],
)
def test_production_rejects_unsafe_configuration(
    tmp_path: Path,
    overrides: dict[str, object],
    expected: str,
) -> None:
    with pytest.raises(ValidationError, match=expected):
        _production_settings(tmp_path, **overrides)


def test_secure_production_configuration_is_accepted(tmp_path: Path) -> None:
    settings = _production_settings(tmp_path)

    assert settings.auth_mode == "oidc"
    assert settings.session_cookie_secure is True
    assert settings.allowed_hosts == ["analytics.example.invalid"]


def test_redis_rate_limit_url_is_required_only_when_selected(tmp_path: Path) -> None:
    assert _settings(tmp_path).rate_limit_redis_url is None
    with pytest.raises(ValidationError, match="RATE_LIMIT_REDIS_URL"):
        _settings(tmp_path, rate_limit_backend="redis")


def test_secret_configuration_is_absent_from_settings_text_and_safe_summary(
    tmp_path: Path,
) -> None:
    sentinel = "SENTINEL-PASSWORD-93481"
    settings = _settings(
        tmp_path,
        database_url=f"postgresql+psycopg://user:{sentinel}@localhost/db",
        query_database_url=f"postgresql+psycopg://reader:{sentinel}@localhost/db",
        session_redis_url=f"redis://:{sentinel}@localhost/0",
        rate_limit_redis_url=f"redis://:{sentinel}@localhost/1",
        gemini_api_key=sentinel,
        azure_openai_api_key=sentinel,
    )

    assert sentinel not in repr(settings)
    assert sentinel not in str(settings)
    assert sentinel not in str(safe_security_summary(settings))


def test_explicit_cors_allowlist_and_untrusted_origin_behavior(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        cors_allowed_origins=["https://trusted.example.invalid"],
    )
    with TestClient(create_app(settings)) as client:
        accepted = client.options(
            "/chat",
            headers={
                "Origin": "https://trusted.example.invalid",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type, X-Tab-Id",
            },
        )
        rejected = client.options(
            "/chat",
            headers={
                "Origin": "https://evil.example.invalid",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert accepted.status_code == 200
    assert accepted.headers["access-control-allow-origin"] == "https://trusted.example.invalid"
    assert accepted.headers["access-control-allow-credentials"] == "true"
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_trusted_and_untrusted_host_headers(tmp_path: Path) -> None:
    settings = _settings(tmp_path, allowed_hosts=["testserver", "trusted.example.invalid"])
    with TestClient(create_app(settings)) as client:
        accepted = client.get("/api/health", headers={"Host": "trusted.example.invalid"})
        rejected = client.get("/api/health", headers={"Host": "evil.example.invalid"})

    assert accepted.status_code == 200
    assert rejected.status_code == 400


def test_security_headers_are_present_and_hsts_is_off_locally(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert "strict-transport-security" not in response.headers


def test_hsts_is_emitted_only_when_explicitly_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, hsts_enabled=True, hsts_max_age_seconds=1234)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/health")

    assert response.headers["strict-transport-security"] == "max-age=1234"


def test_api_docs_remain_local_and_can_be_disabled(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get("/docs").status_code == 200

    production = _production_settings(tmp_path)
    with TestClient(create_app(production)) as client:
        assert client.get("/docs", headers={"Host": "analytics.example.invalid"}).status_code == 404
        assert (
            client.get("/openapi.json", headers={"Host": "analytics.example.invalid"}).status_code
            == 404
        )


def test_request_body_limit_accepts_small_and_rejects_large_or_streamed_bodies(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, request_max_body_bytes=1024)
    with TestClient(create_app(settings)) as client:
        accepted = client.post("/chat/select-mode", json={"mode": "sql"})
        oversized = client.post(
            "/chat/select-mode",
            content=b"x" * 1025,
            headers={"Content-Type": "application/json"},
        )
        streamed = client.post(
            "/chat/select-mode",
            content=iter([b"x" * 600, b"y" * 600]),
            headers={"Content-Type": "application/json"},
        )

    assert accepted.status_code == 200
    for response in (oversized, streamed):
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"


def test_health_is_minimal_public_and_not_rate_limited(tmp_path: Path) -> None:
    settings = _settings(tmp_path, rate_limit_requests=1)
    with TestClient(create_app(settings)) as client:
        responses = [client.get("/api/health") for _ in range(4)]

    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == {"status": "ok"} for response in responses)


def test_validation_errors_do_not_reflect_sensitive_input(tmp_path: Path) -> None:
    sentinel = "SENTINEL-PATIENT-CONTEXT"
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.post(
            "/chat",
            json={"message": f"bad\u0000{sentinel}"},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "The request payload is invalid.",
        }
    }
    assert sentinel not in response.text
