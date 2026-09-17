"""Reusable FastAPI authentication and permission dependencies."""

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import APIError
from app.auth.exceptions import AuthenticationError, PermissionDeniedError
from app.auth.models import AuthPrincipal
from app.auth.permissions import Permission
from app.observability.metrics import get_metrics, route_category

_bearer = HTTPBearer(auto_error=False)


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> AuthPrincipal:
    backend = request.app.state.authentication_backend
    token = credentials.credentials if credentials is not None else None
    try:
        return backend.authenticate(token)
    except AuthenticationError as exc:
        get_metrics().record(
            "auth.authentication_failures",
            1,
            {
                "reason_code": "missing_token" if credentials is None else "invalid_token",
                "route_category": route_category(request.url.path),
            },
        )
        raise APIError(
            status_code=401,
            code="authentication_required",
            message="Authentication is required.",
        ) from exc


CurrentPrincipal = Annotated[AuthPrincipal, Depends(get_current_principal)]


def require_authenticated(principal: CurrentPrincipal) -> AuthPrincipal:
    return principal


def require_permission(permission: Permission):
    """Create a dependency that returns the principal after one permission check."""

    def dependency(request: Request, principal: CurrentPrincipal) -> AuthPrincipal:
        try:
            request.app.state.authorization_service.require_permission(principal, permission)
        except PermissionDeniedError as exc:
            get_metrics().record(
                "auth.authorization_denials",
                1,
                {
                    "reason_code": "permission_denied",
                    "route_category": route_category(request.url.path),
                },
            )
            raise APIError(
                status_code=403,
                code="permission_denied",
                message="You do not have permission to perform this action.",
            ) from exc
        return principal

    return dependency
