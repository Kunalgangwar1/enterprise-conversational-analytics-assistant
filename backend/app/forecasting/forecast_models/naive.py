"""Last-observation baseline."""


class NaiveModel:
    name = "naive"
    minimum_history = 1

    def __init__(self) -> None:
        self._last: float | None = None

    def fit(self, values: tuple[float, ...]) -> None:
        if not values:
            raise ValueError("Naive model requires history")
        self._last = values[-1]

    def predict(self, horizon: int) -> tuple[float, ...]:
        if self._last is None:
            raise RuntimeError("Model must be fitted before prediction")
        return (self._last,) * horizon
