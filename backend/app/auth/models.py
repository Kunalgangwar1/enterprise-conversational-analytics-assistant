"""Typed identity and authorization decision contracts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.auth.permissions import Permission
from app.auth.roles import AppRole


class AuthMethod(StrEnum):
    DEVELOPMENT = "development"
    OIDC = "oidc"


class AuthPrincipal(BaseModel):
    """Normalized identity safe for use by application code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=512)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=256)
    roles: tuple[AppRole, ...] = ()
    groups: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    permissions: frozenset[Permission] = frozenset()
    authentication_method: AuthMethod


class AuthorizationDecision(BaseModel):
    """Safe, testable result of one deterministic permission check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    required_permission: Permission
    reason_code: str


class AuthMeResponse(BaseModel):
    """Frontend-safe current-principal response; tokens and raw claims are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    email: str | None
    display_name: str | None
    roles: tuple[AppRole, ...]
    groups: tuple[str, ...]
    permissions: tuple[Permission, ...]
    auth_method: AuthMethod

    @classmethod
    def from_principal(cls, principal: AuthPrincipal) -> "AuthMeResponse":
        return cls(
            subject=principal.subject,
            email=principal.email,
            display_name=principal.display_name,
            roles=principal.roles,
            groups=principal.groups,
            permissions=tuple(sorted(principal.permissions, key=str)),
            auth_method=principal.authentication_method,
        )
