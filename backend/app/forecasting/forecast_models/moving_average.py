"""Recursive moving-average forecast."""


class MovingAverageModel:
    name = "moving_average"

    def __init__(self, window: int) -> None:
        if window < 2:
            raise ValueError("Moving-average window must be at least 2")
        self.window = window
        self.minimum_history = window
        self._values: list[float] | None = None

    def fit(self, values: tuple[float, ...]) -> None:
        if len(values) < self.minimum_history:
            raise ValueError("Moving-average model has insufficient history")
        self._values = list(values)

    def predict(self, horizon: int) -> tuple[float, ...]:
        if self._values is None:
            raise RuntimeError("Model must be fitted before prediction")
        working = self._values.copy()
        predictions: list[float] = []
        for _ in range(horizon):
            predicted = sum(working[-self.window :]) / self.window
            predictions.append(predicted)
            working.append(predicted)
        return tuple(predictions)
