"""Sanitized failures for unified chat orchestration."""


class ChatError(Exception):
    """Base error safe for application-level translation."""


class InvalidChatStrategyError(ChatError):
    """Raised when a request strategy is incompatible with the selected mode."""


class SpecialistUnavailableError(ChatError):
    """Raised when an internal route has no configured implementation."""


class ChatSQLGenerationError(ChatError):
    """Raised when standard SQL does not produce an accepted final query."""
