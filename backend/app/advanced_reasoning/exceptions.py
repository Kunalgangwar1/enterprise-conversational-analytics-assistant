"""Controlled failures for generic advanced reasoning."""


class AdvancedReasoningError(Exception):
    """Base error for the bounded planner."""


class AdvancedReasoningPlanError(AdvancedReasoningError):
    """Raised when a model-produced plan violates application policy."""


class AdvancedToolUnavailableError(AdvancedReasoningError):
    """Raised when a plan references an unavailable application tool."""


class AdvancedReasoningProviderError(AdvancedReasoningError):
    """Raised when a provider cannot produce required structured output."""


class AdvancedReasoningCitationError(AdvancedReasoningError):
    """Raised when synthesis cites provenance not returned by a tool."""
