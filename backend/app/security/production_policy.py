"""Central fail-closed validation for production security configuration."""

from typing import Protocol


class ProductionSecuritySettings(Protocol):
    app_env: str
    auth_mode: str
    session_cookie_secure: bool
    cors_allowed_origins: list[str]
    cors_allow_credentials: bool
    allowed_hosts: list[str]
    api_docs_enabled: bool
    rate_limit_enabled: bool


def validate_production_security(settings: ProductionSecuritySettings) -> None:
    """Reject combinations that are clearly unsafe in a production environment."""

    if settings.app_env.strip().lower() not in {"production", "prod"}:
        return
    violations: list[str] = []
    if settings.auth_mode == "development":
        violations.append("AUTH_MODE=development")
    if not settings.session_cookie_secure:
        violations.append("SESSION_COOKIE_SECURE=false")
    if settings.cors_allow_credentials and "*" in settings.cors_allowed_origins:
        violations.append("credentialed wildcard CORS")
    if not settings.allowed_hosts or any(
        host.strip() in {"", "*"} for host in settings.allowed_hosts
    ):
        violations.append("empty or wildcard ALLOWED_HOSTS")
    if settings.api_docs_enabled:
        violations.append("API_DOCS_ENABLED=true")
    if not settings.rate_limit_enabled:
        violations.append("RATE_LIMIT_ENABLED=false")
    if violations:
        raise ValueError("Unsafe production configuration: " + ", ".join(violations))


def safe_security_summary(settings: ProductionSecuritySettings) -> dict[str, object]:
    """Return only non-secret security posture fields for diagnostics/tests."""

    return {
        "environment": settings.app_env,
        "auth_mode": settings.auth_mode,
        "session_cookie_secure": settings.session_cookie_secure,
        "cors_origin_count": len(settings.cors_allowed_origins),
        "allowed_host_count": len(settings.allowed_hosts),
        "api_docs_enabled": settings.api_docs_enabled,
    }
