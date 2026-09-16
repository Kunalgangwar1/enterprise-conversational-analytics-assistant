"""Leakage-free deterministic numerical forecasting evaluation."""

from datetime import date, timedelta

from app.evaluation.metrics import mae, rmse, smape
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, ForecastingCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.forecasting.engine import ForecastEngine
from app.forecasting.models import (
    ForecastFrequency,
    ForecastPlan,
    HistoricalTimeSeries,
    TimeSeriesPoint,
)


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    engine = ForecastEngine(
        backtest_points=context.settings.forecast_backtest_points,
        moving_average_window=context.settings.forecast_moving_average_window,
        interval_z=context.settings.forecast_interval_z,
    )
    query_executor = None
    if context.profile.value in {"integration", "live"}:
        from app.db.query.factory import build_query_executor

        query_executor = build_query_executor(context.settings)

    def one(raw_case):
        case = ForecastingCase.model_validate(raw_case)
        frequency = ForecastFrequency(case.frequency)
        values = case.history
        future = case.future
        if query_executor is not None and case.integration_sql:
            extracted = query_executor.execute(case.integration_sql)
            database_values = tuple(float(row["value"]) for row in extracted.rows)
            if len(database_values) < 9:
                raise ValueError("Integration forecast requires at least nine database periods")
            values = database_values[:-3]
            future = database_values[-3:]
        periods = _periods(date(2024, 1, 1), len(values), frequency)
        history = HistoricalTimeSeries(
            frequency=frequency,
            points=tuple(
                TimeSeriesPoint(period=period, value=value)
                for period, value in zip(periods, values, strict=True)
            ),
        )
        plan = ForecastPlan(
            metric_label="Synthetic aggregate",
            frequency=frequency,
            horizon_periods=len(future),
            historical_series_question="Synthetic held-out evaluation series",
        )
        result = engine.compute(plan, history)
        predicted = tuple(item.predicted for item in result.forecast_points)
        selected_mae = mae(future, predicted)
        naive = (values[-1],) * len(future)
        naive_mae = mae(future, naive)
        bounds_valid = all(
            item.lower_bound <= item.predicted <= item.upper_bound
            for item in result.forecast_points
        )
        future_dates = all(
            item.period > history.points[-1].period for item in result.forecast_points
        )
        nonnegative = all(item.lower_bound >= 0 for item in result.forecast_points)
        passed = len(predicted) == len(future) and bounds_valid and future_dates and nonnegative
        return pass_fail(
            case,
            passed,
            metrics={
                "mae": selected_mae,
                "rmse": rmse(future, predicted),
                "smape": smape(future, predicted),
                "naive_mae": naive_mae,
                "relative_improvement": (
                    (naive_mae - selected_mae) / naive_mae if naive_mae else 0.0
                ),
                "invariant_violation": float(not passed),
            },
            expected=f"{len(future)} bounded future points",
            actual=f"{len(predicted)} points from {result.selected_model}",
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "mae": mean_case_metric(items, "mae"),
            "rmse": mean_case_metric(items, "rmse"),
            "smape": mean_case_metric(items, "smape"),
            "naive_mae": mean_case_metric(items, "naive_mae"),
            "relative_improvement": mean_case_metric(items, "relative_improvement"),
            "forecast_invariant_violation_count": sum(
                i.metrics.get("invariant_violation", 0) for i in items
            ),
        },
    )


def _periods(start: date, count: int, frequency: ForecastFrequency) -> tuple[date, ...]:
    result = []
    current = start
    for _ in range(count):
        result.append(current)
        if frequency is ForecastFrequency.DAY:
            current += timedelta(days=1)
        elif frequency is ForecastFrequency.WEEK:
            current += timedelta(weeks=1)
        else:
            current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return tuple(result)
