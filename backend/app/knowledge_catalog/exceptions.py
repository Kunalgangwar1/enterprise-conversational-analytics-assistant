"""Controlled exceptions for Knowledge Catalog loading and retrieval."""

from app.reliability.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class KnowledgeCatalogError(RuntimeError):
    """Base class for provider-neutral catalog failures."""


class CatalogLoadError(KnowledgeCatalogError):
    """Raised when catalog documents cannot be loaded safely."""


class CatalogHierarchyError(KnowledgeCatalogError):
    """Raised when explicit catalog hierarchy metadata is inconsistent."""


class CatalogTraversalError(KnowledgeCatalogError):
    """Raised when a hierarchy traversal response is invalid."""


class EmbeddingError(KnowledgeCatalogError, ProviderError):
    """Base class for provider-neutral embedding failures."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when a requested embedding provider is not configured."""


class EmbeddingAuthenticationError(ProviderAuthenticationError, EmbeddingError):
    """Raised when embedding provider authentication fails."""


class EmbeddingRateLimitError(ProviderRateLimitError, EmbeddingError):
    """Raised when the embedding provider rate limit is exceeded."""


class EmbeddingTimeoutError(ProviderTimeoutError, EmbeddingError):
    """Raised when an embedding request times out."""


class EmbeddingProviderError(EmbeddingError):
    """Raised for other embedding provider failures."""


class EmbeddingUnavailableError(ProviderUnavailableError, EmbeddingProviderError):
    """Raised for transient embedding transport/server failures."""


class EmbeddingRequestError(ProviderRequestError, EmbeddingProviderError):
    """Raised for deterministic invalid embedding requests."""


class EmbeddingIndexMismatchError(EmbeddingError):
    """Raised before searching an index built with incompatible embeddings."""


class KnowledgeIndexError(KnowledgeCatalogError):
    """Raised when the local LanceDB index cannot be read or built."""


class KnowledgeIndexUnavailableError(KnowledgeIndexError):
    """Raised when hybrid retrieval is requested before an index exists."""


class CitationValidationError(KnowledgeCatalogError):
    """Raised when generated citations do not belong to supplied evidence."""
