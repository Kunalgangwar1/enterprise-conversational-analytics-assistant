"""Leakage-free holdout evaluation and deterministic model selection."""

import math
from collections.abc import Callable
from dataclasses import dataclass

from app.forecasting.exceptions import ForecastExecutionError
from app.forecasting.forecast_models import ForecastModel
from app.forecasting.models import ForecastMetrics, ModelEvaluation

ModelFactory = Callable[[], ForecastModel]


@dataclass(frozen=True, slots=True)
class BacktestSelection:
    factory: ModelFactory
    evaluation: ModelEvaluation
    evaluations: tuple[ModelEvaluation, ...]


class BacktestSelector:
    """Evaluate candidates on one chronological holdout and choose by stable policy."""

    def __init__(self, backtest_points: int) -> None:
        self._backtest_points = backtest_points

    def select(
        self,
        values: tuple[float, ...],
        factories: tuple[ModelFactory, ...],
    ) -> BacktestSelection:
        holdout_size = min(self._backtest_points, len(values) - 1)
        training = values[:-holdout_size]
        actual = values[-holdout_size:]
        evaluated: list[tuple[ModelFactory, ModelEvaluation]] = []
        for factory in factories:
            model = factory()
            if len(training) < model.minimum_history:
                continue
            model.fit(training)
            predicted = model.predict(holdout_size)
            evaluated.append(
                (
                    factory,
                    ModelEvaluation(
                        model_name=model.name,
                        metrics=calculate_metrics(actual, predicted),
                    ),
                )
            )
        if not evaluated:
            raise ForecastExecutionError("No forecast model has sufficient training history")
        evaluated.sort(
            key=lambda item: (
                item[1].metrics.mae,
                item[1].metrics.rmse,
                item[1].model_name,
            )
        )
        return BacktestSelection(
            factory=evaluated[0][0],
            evaluation=evaluated[0][1],
            evaluations=tuple(item[1] for item in evaluated),
        )


def calculate_metrics(actual: tuple[float, ...], predicted: tuple[float, ...]) -> ForecastMetrics:
    """Calculate standard error metrics with zero-safe symmetric MAPE."""

    if not actual or len(actual) != len(predicted):
        raise ValueError("Metric inputs must be non-empty and equally sized")
    errors = tuple(
        observed - estimate for observed, estimate in zip(actual, predicted, strict=True)
    )
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error**2 for error in errors) / len(errors))
    smape_terms = []
    for observed, estimate in zip(actual, predicted, strict=True):
        denominator = abs(observed) + abs(estimate)
        smape_terms.append(
            0.0 if denominator == 0 else 200 * abs(observed - estimate) / denominator
        )
    return ForecastMetrics(mae=mae, rmse=rmse, smape=sum(smape_terms) / len(smape_terms))
