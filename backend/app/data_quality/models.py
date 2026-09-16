"""Typed Data Quality evidence and response models."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DataQualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataQualityDocument(DataQualityModel):
    id: NonBlankString
    title: NonBlankString
    topic: NonBlankString
    dimension: str | None = None
    dataset: str | None = None
    source_path: NonBlankString
    text: NonBlankString


class DataQualityEvidence(DataQualityModel):
    evidence_id: NonBlankString
    title: NonBlankString
    topic: NonBlankString
    dimension: str | None = None
    dataset: str | None = None
    source_path: NonBlankString
    text: NonBlankString
    rank: int = Field(ge=1)
    score: float = Field(gt=0, le=1)


class DataQualityGroundedAnswer(DataQualityModel):
    answer: NonBlankString
    citation_ids: list[NonBlankString]

    @model_validator(mode="after")
    def require_unique_citations(self) -> Self:
        if len(self.citation_ids) != len(set(self.citation_ids)):
            raise ValueError("citation_ids must be unique")
        return self


class DataQualityCitation(DataQualityModel):
    id: NonBlankString
    title: NonBlankString
    topic: NonBlankString
    source_path: NonBlankString


class DataQualityResult(DataQualityModel):
    answer: NonBlankString
    citations: tuple[DataQualityCitation, ...] = ()
