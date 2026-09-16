"""Small clean-room role model and explicit permission composition."""

from enum import StrEnum

from app.auth.permissions import Permission


class AppRole(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


VIEWER_PERMISSIONS = frozenset(
    {
        Permission.CHAT_USE,
        Permission.DASHBOARD_READ,
        Permission.DATA_DISCOVERY_READ,
        Permission.KNOWLEDGE_CATALOG_READ,
        Permission.DATA_QUALITY_READ,
        Permission.SEMANTICA_READ,
        Permission.GROUP_ACCESS_READ_SELF,
    }
)

ANALYST_PERMISSIONS = VIEWER_PERMISSIONS | {
    Permission.SQL_GENERATE,
    Permission.SQL_EXECUTE,
    Permission.SQL_ADVANCED,
    Permission.FORECAST_RUN,
}

ROLE_PERMISSIONS: dict[AppRole, frozenset[Permission]] = {
    AppRole.VIEWER: VIEWER_PERMISSIONS,
    AppRole.ANALYST: frozenset(ANALYST_PERMISSIONS),
    AppRole.ADMIN: frozenset(ANALYST_PERMISSIONS | {Permission.ADMIN_AUTHORIZATION_READ}),
}


def normalize_roles(values: object) -> tuple[AppRole, ...]:
    """Normalize configured/provider roles while granting nothing for unknown values."""

    if isinstance(values, str):
        candidates = values.replace(",", " ").split()
    elif isinstance(values, (list, tuple, set, frozenset)):
        candidates = [value for value in values if isinstance(value, str)]
    else:
        candidates = []

    normalized: list[AppRole] = []
    for candidate in candidates:
        try:
            role = AppRole(candidate.strip().lower())
        except ValueError:
            continue
        if role not in normalized:
            normalized.append(role)
    return tuple(normalized)
