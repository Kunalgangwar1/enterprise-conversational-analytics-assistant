"""Controlled failures raised by Phase 23 security boundaries."""


class SecurityBoundaryError(RuntimeError):
    """Base error for infrastructure-independent security controls."""


class RateLimitUnavailableError(SecurityBoundaryError):
    """Raised when a configured shared limiter cannot make a safe decision."""
