"""Sanitized exceptions for the standard NLP-to-SQL pipeline."""


class NLP2SQLError(Exception):
    """Base exception for NLP-to-SQL workflow failures."""


class NLP2SQLMetadataError(NLP2SQLError):
    """Raised when required schema metadata is unavailable."""


class DomainSelectionError(NLP2SQLError):
    """Raised when structured domain selection violates available metadata."""


class TableSelectionError(NLP2SQLError):
    """Raised when structured table selection violates the candidate set."""


class SQLGenerationError(NLP2SQLError):
    """Raised when the LLM does not return a usable SQL string."""


class SQLValidationError(NLP2SQLError):
    """Raised when a validator cannot produce a controlled decision."""


class SQLSchemaValidationError(SQLValidationError):
    """Raised when deterministic schema analysis fails unexpectedly."""


class SQLSemanticValidationError(SQLValidationError):
    """Raised when the semantic assessment provider fails."""
