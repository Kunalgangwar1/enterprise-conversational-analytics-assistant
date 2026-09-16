"""Authentication backend protocol and settings-based construction."""

from typing import Protocol

from app.auth.authorization import AuthorizationService
from app.auth.development import DevelopmentAuthenticationBackend
from app.auth.models import AuthPrincipal
from app.auth.oidc import OIDCAuthenticationBackend
from app.core.config import Settings


class AuthenticationBackend(Protocol):
    def authenticate(self, bearer_token: str | None) -> AuthPrincipal:
        """Authenticate one request without exposing provider-specific claims."""
        ...


def build_authentication_backend(
    settings: Settings,
    authorization: AuthorizationService,
) -> AuthenticationBackend:
    if settings.auth_mode == "development":
        return DevelopmentAuthenticationBackend(settings, authorization)
    return OIDCAuthenticationBackend(settings, authorization)
