"""Standards-compatible signed JWT authentication using issuer JWKS."""

from collections.abc import Callable, Mapping
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWTError

from app.auth.authorization import AuthorizationService
from app.auth.exceptions import AuthenticationError
from app.auth.models import AuthMethod, AuthPrincipal
from app.auth.roles import AppRole, normalize_roles
from app.core.config import Settings

SigningKeyResolver = Callable[[str], Any]


class OIDCAuthenticationBackend:
    """Verify bearer JWTs and normalize provider claims at the auth boundary."""

    def __init__(
        self,
        settings: Settings,
        authorization: AuthorizationService,
        *,
        signing_key_resolver: SigningKeyResolver | None = None,
    ) -> None:
        self._settings = settings
        self._authorization = authorization
        self._algorithms = tuple(
            item.strip() for item in settings.auth_oidc_algorithms.split(",") if item.strip()
        )
        if not self._algorithms:
            raise ValueError("AUTH_OIDC_ALGORITHMS must contain at least one algorithm")
        if signing_key_resolver is None:
            jwks_client = PyJWKClient(settings.auth_oidc_jwks_url or "", cache_keys=True)

            def resolve_signing_key(token: str) -> Any:
                return jwks_client.get_signing_key_from_jwt(token).key

            signing_key_resolver = resolve_signing_key
        self._signing_key_resolver = signing_key_resolver

    def authenticate(self, bearer_token: str | None) -> AuthPrincipal:
        if not bearer_token:
            raise AuthenticationError("A bearer token is required")
        try:
            signing_key = self._signing_key_resolver(bearer_token)
            claims = jwt.decode(
                bearer_token,
                signing_key,
                algorithms=list(self._algorithms),
                issuer=self._settings.auth_oidc_issuer,
                audience=self._settings.auth_oidc_audience,
                options={
                    "require": ["exp", "sub"],
                    "verify_aud": self._settings.auth_oidc_audience is not None,
                },
            )
            principal = self._principal_from_claims(claims)
        except (PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise AuthenticationError("Bearer token validation failed") from exc
        return self._authorization.enrich(principal)

    def _principal_from_claims(self, claims: Mapping[str, Any]) -> AuthPrincipal:
        expected_token_use = self._settings.auth_oidc_token_use
        if expected_token_use is not None and claims.get("token_use") != expected_token_use:
            raise AuthenticationError("Bearer token has an unexpected token use")

        groups = _string_values(claims.get(self._settings.auth_oidc_groups_claim))
        direct_roles = normalize_roles(claims.get(self._settings.auth_oidc_roles_claim))
        mapped_roles = tuple(
            AppRole(role)
            for group in groups
            if (role := self._settings.auth_group_role_mapping.get(group)) is not None
        )
        roles = tuple(dict.fromkeys((*direct_roles, *mapped_roles)))
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("Bearer token subject is missing")
        return AuthPrincipal(
            subject=subject,
            email=_optional_string(claims.get(self._settings.auth_oidc_email_claim)),
            display_name=_optional_string(claims.get(self._settings.auth_oidc_display_name_claim)),
            roles=roles,
            groups=groups,
            scopes=_scope_values(claims.get(self._settings.auth_oidc_scope_claim)),
            authentication_method=AuthMethod.OIDC,
        )


def _string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = [item for item in value if isinstance(item, str)]
    else:
        values = []
    return tuple(dict.fromkeys(item.strip() for item in values if item.strip()))


def _scope_values(value: object) -> tuple[str, ...]:
    return _string_values(value)


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
