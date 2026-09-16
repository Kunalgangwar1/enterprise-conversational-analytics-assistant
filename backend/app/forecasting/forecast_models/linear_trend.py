"""Ordinary least-squares linear trend forecast."""


class LinearTrendModel:
    name = "linear_trend"
    minimum_history = 2

    def __init__(self) -> None:
        self._length: int | None = None
        self._intercept = 0.0
        self._slope = 0.0

    def fit(self, values: tuple[float, ...]) -> None:
        if len(values) < self.minimum_history:
            raise ValueError("Linear trend requires at least two points")
        count = len(values)
        mean_x = (count - 1) / 2
        mean_y = sum(values) / count
        denominator = sum((index - mean_x) ** 2 for index in range(count))
        self._slope = (
            sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
            / denominator
        )
        self._intercept = mean_y - self._slope * mean_x
        self._length = count

    def predict(self, horizon: int) -> tuple[float, ...]:
        if self._length is None:
            raise RuntimeError("Model must be fitted before prediction")
        return tuple(
            self._intercept + self._slope * index
            for index in range(self._length, self._length + horizon)
        )
