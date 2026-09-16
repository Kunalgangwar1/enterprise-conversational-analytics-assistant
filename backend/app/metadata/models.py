"""Typed models used by the metadata subsystem."""

from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MetadataModel(BaseModel):
    """Strict immutable base model for metadata values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnSemanticMetadata(MetadataModel):
    """Business meaning attached to a database column."""

    description: NonBlankString
    aliases: list[NonBlankString] = Field(default_factory=list)
    value_hints: list[NonBlankString] = Field(default_factory=list)
    notes: list[NonBlankString] = Field(default_factory=list)


class DomainMetadata(MetadataModel):
    """A business domain and the application tables it owns."""

    name: NonBlankString
    description: NonBlankString
    aliases: list[NonBlankString] = Field(default_factory=list)
    tables: list[NonBlankString] = Field(min_length=1)


class TableSemanticMetadata(MetadataModel):
    """Business meaning and analytical guidance for one table."""

    name: NonBlankString
    description: NonBlankString
    grain: NonBlankString
    domains: list[NonBlankString] = Field(min_length=1)
    aliases: list[NonBlankString] = Field(default_factory=list)
    columns: dict[NonBlankString, ColumnSemanticMetadata] = Field(default_factory=dict)
    notes: list[NonBlankString] = Field(default_factory=list)


class DomainCatalog(MetadataModel):
    """Validated semantic-domain configuration file."""

    domains: list[DomainMetadata] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_domains(self) -> Self:
        _reject_duplicate_names((domain.name for domain in self.domains), "domain")
        return self


class TableCatalog(MetadataModel):
    """Validated semantic-table configuration file."""

    tables: list[TableSemanticMetadata] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_tables(self) -> Self:
        _reject_duplicate_names((table.name for table in self.tables), "table")
        return self


class PhysicalColumnMetadata(MetadataModel):
    """Database-derived attributes for a column."""

    name: NonBlankString
    data_type: NonBlankString
    nullable: bool
    primary_key: bool = False
    unique: bool = False


class RelationshipMetadata(MetadataModel):
    """A physical foreign-key relationship between application tables."""

    source_table: NonBlankString
    source_columns: list[NonBlankString] = Field(min_length=1)
    target_table: NonBlankString
    target_columns: list[NonBlankString] = Field(min_length=1)
    constraint_name: NonBlankString | None = None

    @model_validator(mode="after")
    def require_matching_column_counts(self) -> Self:
        if len(self.source_columns) != len(self.target_columns):
            raise ValueError("foreign-key source and target column counts must match")
        return self


class PhysicalTableMetadata(MetadataModel):
    """Database-derived metadata for one application table."""

    name: NonBlankString
    columns: list[PhysicalColumnMetadata] = Field(min_length=1)
    relationships: list[RelationshipMetadata] = Field(default_factory=list)
    unique_constraints: list[list[NonBlankString]] = Field(default_factory=list)


class ColumnMetadata(MetadataModel):
    """Merged physical and semantic metadata for a column."""

    name: NonBlankString
    data_type: NonBlankString
    nullable: bool
    primary_key: bool = False
    unique: bool = False
    foreign_keys: list[NonBlankString] = Field(default_factory=list)
    description: NonBlankString | None = None
    aliases: list[NonBlankString] = Field(default_factory=list)
    value_hints: list[NonBlankString] = Field(default_factory=list)
    notes: list[NonBlankString] = Field(default_factory=list)


class TableMetadata(MetadataModel):
    """Merged physical and semantic metadata for a table."""

    name: NonBlankString
    description: NonBlankString
    grain: NonBlankString
    domains: list[NonBlankString]
    aliases: list[NonBlankString] = Field(default_factory=list)
    columns: list[ColumnMetadata]
    relationships: list[RelationshipMetadata] = Field(default_factory=list)
    unique_constraints: list[list[NonBlankString]] = Field(default_factory=list)
    notes: list[NonBlankString] = Field(default_factory=list)


class SchemaMetadata(MetadataModel):
    """Serializable snapshot of the complete merged metadata registry."""

    metadata_version: NonBlankString = "1.0"
    generated_at: datetime
    domains: list[DomainMetadata]
    tables: list[TableMetadata]


def _reject_duplicate_names(names: Iterable[str], object_type: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate {object_type} definitions: {duplicate_list}")
