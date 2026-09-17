"""Provider-neutral exceptions for LLM configuration and requests."""

from app.reliability.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class LLMError(ProviderError):
    """Base exception for the LLM subsystem."""


class LLMConfigurationError(LLMError):
    """Raised when a configured provider cannot be constructed safely."""


class LLMAuthenticationError(ProviderAuthenticationError, LLMError):
    """Raised when the provider rejects configured credentials."""


class LLMRateLimitError(ProviderRateLimitError, LLMError):
    """Raised when the provider rate limit is exhausted."""


class LLMTimeoutError(ProviderTimeoutError, LLMError):
    """Raised when an LLM provider request exceeds its transport timeout."""


class LLMStructuredOutputError(LLMError):
    """Raised when typed structured output is absent or invalid."""


class LLMProviderError(LLMError):
    """Raised for other provider or transport failures."""


class LLMUnavailableError(ProviderUnavailableError, LLMProviderError):
    """Raised for connection failures or transient server unavailability."""


class LLMRequestError(ProviderRequestError, LLMProviderError):
    """Raised for deterministic invalid requests or unsupported resources."""
