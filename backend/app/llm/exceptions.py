"""Provider-neutral exceptions for LLM configuration and requests."""


class LLMError(Exception):
    """Base exception for the LLM subsystem."""


class LLMConfigurationError(LLMError):
    """Raised when a configured provider cannot be constructed safely."""


class LLMAuthenticationError(LLMError):
    """Raised when the provider rejects configured credentials."""


class LLMRateLimitError(LLMError):
    """Raised when the provider rate limit is exhausted."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM provider request exceeds its transport timeout."""


class LLMStructuredOutputError(LLMError):
    """Raised when typed structured output is absent or invalid."""


class LLMProviderError(LLMError):
    """Raised for other provider or transport failures."""
