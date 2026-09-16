"""Typed, chain-of-thought-free contracts for advanced reasoning."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AdvancedReasoningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReasoningExecutionMode(StrEnum):
    STANDARD = "standard"
    ADVANCED = "advanced"


class ReasoningSubtask(AdvancedReasoningModel):
    task_id: NonBlankString
    description: NonBlankString


class ReasoningDecomposition(AdvancedReasoningModel):
    subtasks: tuple[ReasoningSubtask, ...] = Field(min_length=1)


class ToolPlanStep(AdvancedReasoningModel):
    step_id: NonBlankString
    tool_name: NonBlankString
    instruction: NonBlankString
    depends_on: tuple[NonBlankString, ...] = ()


class ToolPlan(AdvancedReasoningModel):
    steps: tuple[ToolPlanStep, ...] = Field(min_length=1)


class ToolExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolExecutionResult(AdvancedReasoningModel):
    step_id: NonBlankString
    tool_name: NonBlankString
    status: ToolExecutionStatus
    summary: NonBlankString
    evidence: str | None = None
    citations: tuple[NonBlankString, ...] = ()
    structured_payload: dict[str, Any] | None = None
    warning: str | None = None


class ReflectionStatus(StrEnum):
    SUFFICIENT = "sufficient"
    NEEDS_MORE = "needs_more"


class ReflectionDecision(AdvancedReasoningModel):
    status: ReflectionStatus
    missing_information: tuple[NonBlankString, ...] = ()
    suggested_additional_tasks: tuple[NonBlankString, ...] = ()


class AdvancedSynthesis(AdvancedReasoningModel):
    answer: NonBlankString
    citation_ids: tuple[NonBlankString, ...] = ()


class AdvancedReasoningResult(AdvancedReasoningModel):
    answer: NonBlankString
    tool_results: tuple[ToolExecutionResult, ...]
    citations: tuple[NonBlankString, ...] = ()
    warnings: tuple[NonBlankString, ...] = ()
