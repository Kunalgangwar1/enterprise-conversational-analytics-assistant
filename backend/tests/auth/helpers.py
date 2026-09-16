"""Small principal/backend fixtures shared by auth tests."""

from app.auth.authorization import AuthorizationService
from app.auth.exceptions import AuthenticationError
from app.auth.models import AuthMethod, AuthPrincipal
from app.auth.roles import AppRole


def principal(
    role: AppRole | None,
    *,
    subject: str = "synthetic-user",
) -> AuthPrincipal:
    roles = () if role is None else (role,)
    return AuthorizationService().enrich(
        AuthPrincipal(
            subject=subject,
            email=f"{subject}@example.invalid",
            display_name=subject.replace("-", " ").title(),
            roles=roles,
            groups=("synthetic-group",),
            authentication_method=AuthMethod.OIDC,
        )
    )


class FixedAuthenticationBackend:
    def __init__(self, value: AuthPrincipal | None) -> None:
        self.principal = value

    def authenticate(self, _bearer_token: str | None) -> AuthPrincipal:
        if self.principal is None:
            raise AuthenticationError("No authenticated principal")
        return self.principal
