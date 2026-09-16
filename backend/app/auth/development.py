"""Deterministic identity for local development and automated tests only."""

from app.auth.authorization import AuthorizationService
from app.auth.models import AuthMethod, AuthPrincipal
from app.auth.roles import normalize_roles
from app.core.config import Settings


class DevelopmentAuthenticationBackend:
    def __init__(self, settings: Settings, authorization: AuthorizationService) -> None:
        if settings.app_env.strip().lower() not in {"local", "development", "dev", "test"}:
            raise ValueError("Development authentication is restricted to local/test environments")
        principal = AuthPrincipal(
            subject=settings.auth_dev_subject,
            email=settings.auth_dev_email,
            display_name=settings.auth_dev_display_name,
            roles=normalize_roles(settings.auth_dev_roles),
            authentication_method=AuthMethod.DEVELOPMENT,
        )
        self._principal = authorization.enrich(principal)

    def authenticate(self, _bearer_token: str | None) -> AuthPrincipal:
        """Return only the configured identity; request headers cannot impersonate users."""

        return self._principal
