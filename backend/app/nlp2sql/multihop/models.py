"""Typed models for bounded multi-hop SQL analysis."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TableCell = str | int | float | bool | None


class MultiHopModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HopPlan(MultiHopModel):
    hop_id: NonBlankString
    sub_question: NonBlankString
    depends_on: tuple[NonBlankString, ...] = ()
    purpose: NonBlankString


class MultiHopPlan(MultiHopModel):
    hops: tuple[HopPlan, ...] = Field(min_length=1)


class HopExecutionStatus(StrEnum):
    SUCCESS = "success"


class HopResult(MultiHopModel):
    hop_id: NonBlankString
    sub_question: NonBlankString
    selected_domains: tuple[NonBlankString, ...]
    selected_tables: tuple[NonBlankString, ...]
    safe_sql: NonBlankString
    columns: tuple[NonBlankString, ...]
    protected_preview: NonBlankString
    row_count: int = Field(ge=0)
    truncated: bool
    elapsed_ms: float = Field(ge=0)
    status: HopExecutionStatus = HopExecutionStatus.SUCCESS


class MultiHopBudgetSnapshot(MultiHopModel):
    hops_planned: int = Field(ge=1)
    hops_executed: int = Field(ge=0)
    rows_per_hop: tuple[int, ...]
    total_rows_returned: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)


class SynthesisTable(MultiHopModel):
    columns: tuple[NonBlankString, ...] = ()
    rows: tuple[tuple[TableCell, ...], ...] = ()

    @model_validator(mode="after")
    def require_row_widths(self) -> "SynthesisTable":
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Synthesis table row width must match its columns")
        return self


class DeltaDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"


class DeltaAnnotation(MultiHopModel):
    label: NonBlankString
    value: float
    unit: NonBlankString
    direction: DeltaDirection | None = None


class MultiHopSynthesis(MultiHopModel):
    summary: NonBlankString
    table: SynthesisTable = Field(default_factory=SynthesisTable)
    deltas: tuple[DeltaAnnotation, ...] = ()


class MultiHopResult(MultiHopModel):
    answer_markdown: NonBlankString
    synthesis: MultiHopSynthesis
    hops: tuple[HopResult, ...]
    budget: MultiHopBudgetSnapshot
    incomplete: bool = False
