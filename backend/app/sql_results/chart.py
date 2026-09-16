"""Conservative deterministic chart recommendation from returned Python values."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.db.query.models import QueryExecutionResult
from app.sql_results.models import ChartMetadata, ChartType


class _ColumnRole(StrEnum):
    NUMERIC = "numeric"
    TEMPORAL = "temporal"
    CATEGORICAL = "categorical"
    UNKNOWN = "unknown"


class ChartMetadataBuilder:
    """Choose a basic chart from actual values and conservative name heuristics."""

    def build(self, result: QueryExecutionResult) -> ChartMetadata:
        if result.row_count == 0:
            return ChartMetadata(
                chart_type=ChartType.TABLE,
                title="No matching rows",
                selection_rule="empty_result",
            )

        roles = {
            column: _infer_role([row.get(column) for row in result.rows])
            for column in result.columns
        }
        numeric = [
            column
            for column in result.columns
            if roles[column] is _ColumnRole.NUMERIC and not _is_identifier_column(column)
        ]
        temporal = [column for column in result.columns if roles[column] is _ColumnRole.TEMPORAL]
        categorical = [
            column for column in result.columns if roles[column] is _ColumnRole.CATEGORICAL
        ]

        if temporal and numeric:
            return _axis_chart(ChartType.LINE, temporal[0], numeric, "temporal_numeric")
        if categorical and numeric:
            return _axis_chart(ChartType.BAR, categorical[0], numeric, "categorical_numeric")
        if len(numeric) >= 2:
            return ChartMetadata(
                chart_type=ChartType.SCATTER,
                x_axis=numeric[0],
                y_axes=(numeric[1],),
                title=f"{_label(numeric[1])} by {_label(numeric[0])}",
                selection_rule="two_numeric_metrics",
            )
        return ChartMetadata(
            chart_type=ChartType.TABLE,
            title="Query result",
            selection_rule="conservative_fallback",
        )


def _axis_chart(
    chart_type: ChartType,
    x_axis: str,
    y_axes: list[str],
    selection_rule: str,
) -> ChartMetadata:
    metric_title = " and ".join(_label(column) for column in y_axes)
    return ChartMetadata(
        chart_type=chart_type,
        x_axis=x_axis,
        y_axes=tuple(y_axes),
        title=f"{metric_title} by {_label(x_axis)}",
        selection_rule=selection_rule,
    )


def _infer_role(values: list[Any]) -> _ColumnRole:
    non_null = [value for value in values if value is not None]
    if not non_null:
        return _ColumnRole.UNKNOWN
    if all(isinstance(value, (datetime, date)) for value in non_null):
        return _ColumnRole.TEMPORAL
    if all(
        isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
        for value in non_null
    ):
        return _ColumnRole.NUMERIC
    if all(isinstance(value, (str, bool)) for value in non_null):
        return _ColumnRole.CATEGORICAL
    return _ColumnRole.UNKNOWN


def _is_identifier_column(column: str) -> bool:
    normalized = column.casefold()
    return normalized == "id" or normalized.endswith("_id")


def _label(column: str) -> str:
    return column.replace("_", " ").strip().title()
