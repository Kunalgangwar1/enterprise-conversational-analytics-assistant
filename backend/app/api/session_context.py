"""Shared request-to-session coordination for tab-isolated APIs."""

from fastapi import Request, Response

from app.api.errors import APIError
from app.core.config import Settings
from app.sessions.exceptions import InvalidTabIdError
from app.sessions.identity import ResolvedSessionIdentity, resolve_session_identity
from app.sessions.service import SessionService


def resolve_request_identity(request: Request) -> tuple[Settings, ResolvedSessionIdentity]:
    """Resolve the configured cookie and tab header into one validated identity."""

    settings: Settings = request.app.state.settings
    browser_cookie = request.cookies.get(settings.session_cookie_name)
    tab_header = request.headers.get(settings.tab_id_header)
    try:
        resolved = resolve_session_identity(browser_cookie, tab_header)
    except InvalidTabIdError as exc:
        raise APIError(
            status_code=400,
            code="invalid_tab_id",
            message=str(exc),
        ) from exc
    return settings, resolved


def get_session_service(request: Request) -> SessionService:
    """Return the application-injected session service."""

    return request.app.state.session_service


def set_browser_cookie(
    response: Response,
    settings: Settings,
    resolved: ResolvedSessionIdentity,
) -> None:
    """Set the opaque browser cookie only when identity resolution created it."""

    if not resolved.is_new_browser_session:
        return
    response.set_cookie(
        key=settings.session_cookie_name,
        value=resolved.identity.browser_session_id,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def session_storage_api_error() -> APIError:
    """Return the shared sanitized persistence error."""

    return APIError(
        status_code=500,
        code="session_storage_error",
        message="Session state could not be accessed safely",
    )
