"""Typed contracts for deterministic dataset discovery."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DiscoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetRegistration(DiscoveryModel):
    dataset: NonBlankString
    repository: NonBlankString
    table: NonBlankString
    domain: NonBlankString
    description: NonBlankString
    table_aliases: tuple[NonBlankString, ...] = ()
    columns: dict[NonBlankString, tuple[NonBlankString, ...]]


class DatasetRegistryConfig(DiscoveryModel):
    datasets: list[dict[str, str]] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_dataset_and_table_names(self) -> Self:
        for key in ("dataset", "table"):
            values = [item.get(key) for item in self.datasets]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate discovery {key} registration")
        return self


class DatasetMatch(DiscoveryModel):
    dataset: NonBlankString
    repository: NonBlankString
    table: NonBlankString
    domain: NonBlankString
    description: NonBlankString
    matched_fields: tuple[NonBlankString, ...]
    score: float = Field(gt=0, le=1)


class DataDiscoveryResult(DiscoveryModel):
    matches: tuple[DatasetMatch, ...] = ()
