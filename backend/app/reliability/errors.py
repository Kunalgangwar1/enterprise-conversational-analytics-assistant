"""Safe provider-neutral reliability error taxonomy."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


class ProviderError(Exception):
    """Base error carrying only safe retry metadata."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(ProviderError):
    """A provider operation exceeded a transport or operation timeout."""


class ProviderRateLimitError(ProviderError):
    """A provider rejected a request because its rate limit was reached."""


class ProviderUnavailableError(ProviderError):
    """A connection or transient provider/server failure occurred."""


class ProviderAuthenticationError(ProviderError):
    """Configured credentials were rejected; retrying cannot repair them."""


class ProviderRequestError(ProviderError):
    """The provider rejected a deterministic request or model configuration."""


class CircuitOpenError(ProviderUnavailableError):
    """A local circuit rejected a call before reaching the provider."""


def retry_after_from_exception(error: Exception, *, now: datetime | None = None) -> float | None:
    """Extract a bounded Retry-After delta without retaining a provider response."""

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        headers = getattr(error, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(str(raw))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            seconds = (retry_at - (now or datetime.now(UTC))).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(300.0, max(0.0, seconds))
