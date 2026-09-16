"""Fixed-period seasonal naive forecast."""


class SeasonalNaiveModel:
    name = "seasonal_naive"

    def __init__(self, season_length: int) -> None:
        if season_length < 2:
            raise ValueError("Season length must be at least 2")
        self.season_length = season_length
        self.minimum_history = season_length
        self._season: tuple[float, ...] | None = None

    def fit(self, values: tuple[float, ...]) -> None:
        if len(values) < self.minimum_history:
            raise ValueError("Seasonal naive model has insufficient history")
        self._season = values[-self.season_length :]

    def predict(self, horizon: int) -> tuple[float, ...]:
        if self._season is None:
            raise RuntimeError("Model must be fitted before prediction")
        return tuple(self._season[index % self.season_length] for index in range(horizon))
