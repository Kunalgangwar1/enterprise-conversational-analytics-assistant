"""Controlled Data Quality specialist failures."""


class DataQualityError(RuntimeError):
    """Base class for Data Quality knowledge failures."""


class DataQualityLoadError(DataQualityError):
    """Raised when the synthetic guidance corpus is malformed."""


class DataQualityCitationError(DataQualityError):
    """Raised when an answer cites evidence that was not supplied."""
