"""Controlled Semantica graph failures."""


class SemanticaError(RuntimeError):
    """Base class for Semantica failures."""


class SemanticaGraphError(SemanticaError):
    """Raised when a persisted or generated adjacency graph is invalid."""


class SemanticaCitationError(SemanticaError):
    """Raised when generated citations are outside supplied evidence."""
