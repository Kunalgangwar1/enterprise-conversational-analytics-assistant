"""Controlled failures raised by deterministic dashboard services."""


class DashboardError(Exception):
    """Base class for dashboard application failures."""


class DashboardDateRangeError(DashboardError, ValueError):
    """Raised when dashboard date inputs are malformed or reversed."""


class DashboardDataUnavailableError(DashboardError):
    """Raised when no dataset-relative default range can be derived."""
