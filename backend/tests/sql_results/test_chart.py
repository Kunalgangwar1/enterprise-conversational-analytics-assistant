"""Deterministic conservative chart metadata tests."""

from datetime import date
from decimal import Decimal

import pytest

from app.db.query.models import QueryExecutionResult
from app.sql_results import ChartMetadataBuilder, ChartType


def _result(columns: list[str], rows: list[dict[str, object]]) -> QueryExecutionResult:
    return QueryExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        elapsed_ms=1,
    )


def test_empty_result_recommends_table() -> None:
    chart = ChartMetadataBuilder().build(_result(["specialty"], []))

    assert chart.chart_type is ChartType.TABLE
    assert chart.x_axis is None
    assert chart.y_axes == ()


def test_categorical_with_multiple_numeric_metrics_recommends_bar() -> None:
    result = _result(
        ["specialty", "claim_count", "total_paid_amount"],
        [
            {"specialty": "Cardiology", "claim_count": 4, "total_paid_amount": Decimal("20")},
            {"specialty": "Primary Care", "claim_count": 6, "total_paid_amount": Decimal("30")},
        ],
    )

    chart = ChartMetadataBuilder().build(result)

    assert chart.chart_type is ChartType.BAR
    assert chart.x_axis == "specialty"
    assert chart.y_axes == ("claim_count", "total_paid_amount")


def test_temporal_and_numeric_recommends_line() -> None:
    result = _result(
        ["month", "claim_count"],
        [
            {"month": date(2026, 1, 1), "claim_count": 4},
            {"month": date(2026, 2, 1), "claim_count": 6},
        ],
    )

    chart = ChartMetadataBuilder().build(result)

    assert chart.chart_type is ChartType.LINE
    assert chart.x_axis == "month"
    assert chart.y_axes == ("claim_count",)


def test_two_meaningful_numeric_columns_recommend_scatter() -> None:
    chart = ChartMetadataBuilder().build(
        _result(
            ["allowed_amount", "paid_amount"],
            [
                {"allowed_amount": Decimal("10"), "paid_amount": Decimal("8")},
                {"allowed_amount": Decimal("20"), "paid_amount": Decimal("15")},
            ],
        )
    )

    assert chart.chart_type is ChartType.SCATTER
    assert chart.x_axis == "allowed_amount"
    assert chart.y_axes == ("paid_amount",)


def test_numeric_identifier_is_not_selected_as_metric() -> None:
    chart = ChartMetadataBuilder().build(
        _result(
            ["provider_id", "specialty"],
            [{"provider_id": 1, "specialty": "Cardiology"}],
        )
    )

    assert chart.chart_type is ChartType.TABLE
    assert chart.y_axes == ()


@pytest.mark.parametrize(
    ("columns", "rows"),
    [
        (["mixed"], [{"mixed": "one"}, {"mixed": 2}]),
        (["flag", "label"], [{"flag": True, "label": "synthetic"}]),
        (["value"], [{"value": 1.5}]),
    ],
)
def test_uncertain_or_unsupported_results_prefer_table_deterministically(
    columns: list[str],
    rows: list[dict[str, object]],
) -> None:
    builder = ChartMetadataBuilder()

    assert builder.build(_result(columns, rows)) == builder.build(_result(columns, rows))
    assert builder.build(_result(columns, rows)).chart_type is ChartType.TABLE
