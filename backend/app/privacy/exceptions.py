"""Sanitized errors raised by the internal privacy boundary."""


class PrivacyError(Exception):
    """Base exception for deterministic privacy processing failures."""


class PrivacyProcessingError(PrivacyError):
    """Raised when protected spans cannot be processed safely."""


class PrivacyUnmaskingError(PrivacyError):
    """Raised when a response mapping is internally inconsistent."""
