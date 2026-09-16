"""Central role-to-permission mapping and authorization policy."""

from collections.abc import Iterable

from app.auth.exceptions import PermissionDeniedError
from app.auth.models import AuthorizationDecision, AuthPrincipal
from app.auth.permissions import Permission
from app.auth.roles import ROLE_PERMISSIONS, AppRole


class AuthorizationService:
    """Evaluate explicit permissions without role-specific bypasses."""

    def effective_permissions(self, roles: Iterable[AppRole]) -> frozenset[Permission]:
        permissions: set[Permission] = set()
        for role in roles:
            permissions.update(ROLE_PERMISSIONS.get(role, frozenset()))
        return frozenset(permissions)

    def enrich(self, principal: AuthPrincipal) -> AuthPrincipal:
        """Attach effective permissions derived only from recognized application roles."""

        return principal.model_copy(
            update={"permissions": self.effective_permissions(principal.roles)}
        )

    def decide(
        self,
        principal: AuthPrincipal,
        permission: Permission,
    ) -> AuthorizationDecision:
        allowed = permission in principal.permissions
        return AuthorizationDecision(
            allowed=allowed,
            required_permission=permission,
            reason_code="permission_granted" if allowed else "permission_missing",
        )

    def has_permission(self, principal: AuthPrincipal, permission: Permission) -> bool:
        return self.decide(principal, permission).allowed

    def require_permission(self, principal: AuthPrincipal, permission: Permission) -> None:
        if not self.has_permission(principal, permission):
            raise PermissionDeniedError("The authenticated principal lacks a required permission")
