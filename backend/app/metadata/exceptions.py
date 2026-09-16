"""Domain-specific exceptions for metadata loading and validation."""


class MetadataError(Exception):
    """Base exception for the metadata subsystem."""


class MetadataConfigurationError(MetadataError):
    """Raised when semantic metadata configuration cannot be loaded."""


class MetadataIntrospectionError(MetadataError):
    """Raised when physical database metadata cannot be inspected."""


class MetadataValidationError(MetadataError):
    """Raised when physical and semantic metadata disagree."""


class MetadataNotFoundError(MetadataError, KeyError):
    """Raised when a requested metadata object is not registered."""


class MetadataRefreshError(MetadataError):
    """Raised when a metadata snapshot cannot be written."""
