"""Clean-room role/permission matrix tests."""

import pytest

from app.auth.authorization import AuthorizationService
from app.auth.permissions import Permission
from app.auth.roles import AppRole, normalize_roles


@pytest.mark.parametrize(
    ("role", "allowed", "denied"),
    [
        (
            AppRole.VIEWER,
            {
                Permission.CHAT_USE,
                Permission.DASHBOARD_READ,
                Permission.DATA_DISCOVERY_READ,
                Permission.KNOWLEDGE_CATALOG_READ,
                Permission.DATA_QUALITY_READ,
                Permission.SEMANTICA_READ,
                Permission.GROUP_ACCESS_READ_SELF,
            },
            {
                Permission.SQL_GENERATE,
                Permission.SQL_EXECUTE,
                Permission.SQL_ADVANCED,
                Permission.FORECAST_RUN,
                Permission.ADMIN_AUTHORIZATION_READ,
            },
        ),
        (
            AppRole.ANALYST,
            set(Permission) - {Permission.ADMIN_AUTHORIZATION_READ},
            {Permission.ADMIN_AUTHORIZATION_READ},
        ),
        (AppRole.ADMIN, set(Permission), set()),
    ],
)
def test_explicit_role_permission_matrix(
    role: AppRole,
    allowed: set[Permission],
    denied: set[Permission],
) -> None:
    permissions = AuthorizationService().effective_permissions((role,))
    assert permissions == allowed
    assert not (permissions & denied)


def test_unknown_external_role_grants_no_permission() -> None:
    assert normalize_roles(["analyst", "unknown-admin", "SUPERUSER"]) == (AppRole.ANALYST,)
    assert normalize_roles(["unknown-admin"]) == ()
    assert AuthorizationService().effective_permissions(()) == frozenset()
