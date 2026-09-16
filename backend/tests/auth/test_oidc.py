"""Offline cryptographic OIDC/JWT verifier tests using ephemeral test keys."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClientError

from app.auth.authorization import AuthorizationService
from app.auth.exceptions import AuthenticationError
from app.auth.oidc import OIDCAuthenticationBackend
from app.auth.permissions import Permission
from app.auth.roles import AppRole
from app.core.config import Settings

ISSUER = "https://identity.example.invalid/test"
AUDIENCE = "enterprise-analytics-test"


@pytest.fixture(scope="module")
def signing_keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "production",
        "auth_mode": "oidc",
        "auth_oidc_issuer": ISSUER,
        "auth_oidc_audience": AUDIENCE,
        "auth_oidc_jwks_url": "https://identity.example.invalid/.well-known/jwks.json",
        "auth_group_role_mapping": {"analytics-viewers": "viewer"},
        "session_cookie_secure": True,
        "api_docs_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def _claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "sub": "oidc-user",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "roles": ["analyst"],
    }
    values.update(overrides)
    return values


def _token(private_key, *, claims: dict[str, object] | None = None, algorithm="RS256") -> str:
    key = private_key if algorithm == "RS256" else "test-only-hmac-secret-at-least-32-bytes"
    return jwt.encode(claims or _claims(), key, algorithm=algorithm, headers={"kid": "test-key"})


def _backend(public_key, **settings: object) -> OIDCAuthenticationBackend:
    return OIDCAuthenticationBackend(
        _settings(**settings),
        AuthorizationService(),
        signing_key_resolver=lambda _token: public_key,
    )


def test_valid_signed_token_is_normalized(signing_keys) -> None:
    private, public = signing_keys
    token = _token(
        private,
        claims=_claims(
            roles=["unknown-role"],
            groups=["analytics-viewers", "external-only"],
            scope="openid catalog.read",
            email="user@example.invalid",
            name="Synthetic User",
        ),
    )

    principal = _backend(public).authenticate(token)

    assert principal.subject == "oidc-user"
    assert principal.roles == (AppRole.VIEWER,)
    assert principal.groups == ("analytics-viewers", "external-only")
    assert principal.scopes == ("openid", "catalog.read")
    assert Permission.DASHBOARD_READ in principal.permissions
    assert Permission.SQL_GENERATE not in principal.permissions


@pytest.mark.parametrize(
    "claims",
    [
        _claims(exp=datetime.now(UTC) - timedelta(seconds=1)),
        _claims(iss="https://wrong.example.invalid"),
        _claims(aud="wrong-client"),
        {key: value for key, value in _claims().items() if key != "sub"},
        _claims(nbf=datetime.now(UTC) + timedelta(minutes=5)),
    ],
    ids=["expired", "wrong-issuer", "wrong-audience", "missing-sub", "future-nbf"],
)
def test_invalid_registered_claims_are_rejected(signing_keys, claims) -> None:
    private, public = signing_keys
    with pytest.raises(AuthenticationError):
        _backend(public).authenticate(_token(private, claims=claims))


def test_unsupported_algorithm_is_rejected(signing_keys) -> None:
    _, public = signing_keys
    token = _token(None, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        _backend(public).authenticate(token)


def test_tampered_signature_is_rejected(signing_keys) -> None:
    _, public = signing_keys
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthenticationError):
        _backend(public).authenticate(_token(other_private))


def test_unknown_signing_key_is_rejected(signing_keys) -> None:
    private, _ = signing_keys
    backend = OIDCAuthenticationBackend(
        _settings(),
        AuthorizationService(),
        signing_key_resolver=lambda _token: (_ for _ in ()).throw(
            PyJWKClientError("unknown test key")
        ),
    )
    with pytest.raises(AuthenticationError):
        backend.authenticate(_token(private))


def test_expected_token_use_is_enforced(signing_keys) -> None:
    private, public = signing_keys
    backend = _backend(public, auth_oidc_token_use="access")
    with pytest.raises(AuthenticationError):
        backend.authenticate(_token(private, claims=_claims(token_use="id")))
