"""Database- and provider-neutral SQL analytics result models."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SQLResultModel(BaseModel):
    """Strict immutable base for result presentation contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SQLResultSummary(SQLResultModel):
    """Concise structured output requested from the summary model."""

    summary: NonBlankString


class SummarySource(StrEnum):
    """Origin of the user-facing result summary."""

    LLM = "llm"
    DETERMINISTIC = "deterministic"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class ChartType(StrEnum):
    """Initial deterministic visualization recommendations."""

    TABLE = "table"
    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"


class ChartMetadata(SQLResultModel):
    """UI-neutral chart recommendation; no rendering configuration."""

    chart_type: ChartType
    x_axis: str | None = None
    y_axes: tuple[str, ...] = ()
    title: NonBlankString
    selection_rule: NonBlankString


class SQLAnalyticsResult(SQLResultModel):
    """Bounded executed rows plus safe summary and chart metadata."""

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool
    execution_elapsed_ms: float = Field(ge=0)
    summary: NonBlankString
    summary_source: SummarySource
    chart: ChartMetadata
