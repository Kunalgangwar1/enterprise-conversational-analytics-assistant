"""Development authentication safety tests."""

import pytest
from pydantic import ValidationError

from app.auth.authorization import AuthorizationService
from app.auth.development import DevelopmentAuthenticationBackend
from app.auth.permissions import Permission
from app.auth.roles import AppRole
from app.core.config import Settings


def test_development_principal_is_deterministic_and_network_free() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="development",
        auth_dev_subject="local-test-user",
        auth_dev_email="developer@example.invalid",
        auth_dev_display_name="Local Test User",
        auth_dev_roles="viewer,unknown-role",
    )
    backend = DevelopmentAuthenticationBackend(settings, AuthorizationService())

    first = backend.authenticate(None)
    second = backend.authenticate("ignored-browser-token")

    assert first == second
    assert first.subject == "local-test-user"
    assert first.roles == (AppRole.VIEWER,)
    assert Permission.SQL_GENERATE not in first.permissions


def test_development_auth_is_rejected_in_production_configuration() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=development"):
        Settings(_env_file=None, app_env="production", auth_mode="development")
