"""Controlled Data Discovery failures."""


class DataDiscoveryError(RuntimeError):
    """Base class for deterministic discovery failures."""


class DataDiscoveryConfigurationError(DataDiscoveryError):
    """Raised when dataset registration is missing or inconsistent."""
