"""Sanitized errors raised by internal supervisor routing."""


class RoutingError(Exception):
    """Base exception for route selection failures."""


class RoutingConfigurationError(RoutingError):
    """Raised when routing configuration cannot be loaded or validated."""


class RoutingUnavailableError(RoutingError):
    """Raised when policy cannot select an enabled internal route."""


class RoutingClassificationError(RoutingError):
    """Raised when structured intent classification is invalid."""


class RoutingProviderError(RoutingError):
    """Raised when required LLM intent classification is unavailable."""
