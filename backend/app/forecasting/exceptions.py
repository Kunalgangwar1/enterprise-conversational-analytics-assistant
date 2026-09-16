"""Provider-neutral forecasting failures."""


class ForecastingError(Exception):
    """Base forecasting failure."""


class ForecastPlanningError(ForecastingError):
    """Raised when a valid structured forecast plan cannot be obtained."""


class ForecastScopeError(ForecastingError):
    """Raised for unsupported individual clinical prediction requests."""


class ForecastHorizonError(ForecastPlanningError):
    """Raised when a requested horizon exceeds application policy."""


class InsufficientHistoryError(ForecastingError):
    """Raised when too few historical observations are available."""


class IrregularTimeSeriesError(ForecastingError):
    """Raised for duplicate, missing, future, or irregular periods."""


class ForecastDataShapeError(ForecastingError):
    """Raised when query rows are not one temporal plus one numeric column."""


class ForecastExecutionError(ForecastingError):
    """Raised when validated historical SQL cannot be executed."""
