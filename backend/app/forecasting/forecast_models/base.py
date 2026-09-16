"""Contract for small deterministic univariate forecasting models."""

from typing import Protocol


class ForecastModel(Protocol):
    name: str
    minimum_history: int

    def fit(self, values: tuple[float, ...]) -> None: ...

    def predict(self, horizon: int) -> tuple[float, ...]: ...
