"""Provider-neutral structured values for standard NLP-to-SQL."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class NLP2SQLModel(BaseModel):
    """Strict immutable base model for workflow values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DomainSelection(NLP2SQLModel):
    """Structured selection of business metadata domains."""

    selected_domains: list[NonBlankString]


class TableSelection(NLP2SQLModel):
    """Structured selection of physical tables from the candidate set."""

    selected_tables: list[NonBlankString]


class SQLGeneration(NLP2SQLModel):
    """Structured PostgreSQL generation output without reasoning text."""

    sql: NonBlankString


class SQLValidationDecision(StrEnum):
    """Terminal or corrective outcome chosen by application policy."""

    ACCEPT = "accept"
    REWRITE = "rewrite"
    REJECT = "reject"


class SQLSemanticAssessment(NLP2SQLModel):
    """Bounded semantic assessment returned by the configured LLM client."""

    score: float = Field(ge=0, le=1)
    issues: list[NonBlankString] = Field(default_factory=list)
    rewrite_guidance: NonBlankString | None = None


class SQLValidationResult(NLP2SQLModel):
    """Application-owned outcome from all SQL validation layers."""

    decision: SQLValidationDecision
    score: float = Field(ge=0, le=1)
    issues: tuple[NonBlankString, ...] = ()
    rewrite_guidance: NonBlankString | None = None
    attempt: int = Field(ge=1)
    reason_code: NonBlankString | None = None
    semantic_assessed: bool = False


class NLP2SQLResult(NLP2SQLModel):
    """Validated but unexecuted result of the Phase 12 graph."""

    selected_domains: tuple[NonBlankString, ...]
    selected_tables: tuple[NonBlankString, ...]
    initial_sql: NonBlankString
    generated_sql: NonBlankString
    final_sql: NonBlankString | None = None
    validation: SQLValidationResult
    generation_attempt: int = Field(ge=1)
    rewrite_count: int = Field(ge=0, le=1)
    llm_call_count: int = Field(ge=0)
