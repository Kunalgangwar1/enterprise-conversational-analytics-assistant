"""Validated in-memory registry combining physical and semantic metadata."""

from collections.abc import Iterable
from datetime import datetime
from types import MappingProxyType
from typing import TypeVar

from app.metadata.context_builder import build_metadata_context
from app.metadata.exceptions import MetadataNotFoundError, MetadataValidationError
from app.metadata.models import (
    ColumnMetadata,
    DomainMetadata,
    PhysicalTableMetadata,
    RelationshipMetadata,
    SchemaMetadata,
    TableMetadata,
    TableSemanticMetadata,
)

NamedMetadata = TypeVar(
    "NamedMetadata",
    DomainMetadata,
    TableSemanticMetadata,
    PhysicalTableMetadata,
)


class MetadataRegistry:
    """Read-only metadata lookup service with schema-drift validation."""

    def __init__(
        self,
        domains: Iterable[DomainMetadata],
        semantic_tables: Iterable[TableSemanticMetadata],
        physical_tables: Iterable[PhysicalTableMetadata],
    ) -> None:
        domain_map = _unique_by_name(domains, "domain")
        semantic_map = _unique_by_name(semantic_tables, "semantic table")
        physical_map = _unique_by_name(physical_tables, "physical table")
        _validate_metadata(domain_map, semantic_map, physical_map)

        merged_tables = {
            name: _merge_table(physical_map[name], semantic_map[name])
            for name in sorted(physical_map)
        }
        self._domains = MappingProxyType(domain_map)
        self._tables = MappingProxyType(merged_tables)

    def list_domains(self) -> tuple[DomainMetadata, ...]:
        """Return all domains in deterministic order."""

        return tuple(self._domains[name] for name in sorted(self._domains))

    def list_tables(self) -> tuple[TableMetadata, ...]:
        """Return all merged tables in deterministic order."""

        return tuple(self._tables[name] for name in sorted(self._tables))

    def get_domain(self, name: str) -> DomainMetadata:
        """Look up a domain by its configured name."""

        try:
            return self._domains[name]
        except KeyError as exc:
            raise MetadataNotFoundError(f"unknown metadata domain: {name}") from exc

    def get_table(self, name: str) -> TableMetadata:
        """Look up a table by its physical name."""

        try:
            return self._tables[name]
        except KeyError as exc:
            raise MetadataNotFoundError(f"unknown metadata table: {name}") from exc

    def tables_for_domain(self, domain_name: str) -> tuple[TableMetadata, ...]:
        """Return the tables mapped to a business domain."""

        domain = self.get_domain(domain_name)
        return tuple(self.get_table(name) for name in sorted(domain.tables))

    def get_relationships(self, table_name: str | None = None) -> tuple[RelationshipMetadata, ...]:
        """Return all relationships, or only outgoing relationships for one table."""

        if table_name is not None:
            return tuple(self.get_table(table_name).relationships)
        return tuple(
            relationship for table in self.list_tables() for relationship in table.relationships
        )

    def build_context(self, table_names: Iterable[str]) -> str:
        """Render deterministic context for exactly the requested table names."""

        unique_names = sorted(set(table_names))
        return build_metadata_context(self.get_table(name) for name in unique_names)

    def to_schema_metadata(self, *, generated_at: datetime) -> SchemaMetadata:
        """Create a serializable snapshot model from the registry."""

        return SchemaMetadata(
            generated_at=generated_at,
            domains=list(self.list_domains()),
            tables=list(self.list_tables()),
        )


def _unique_by_name(items: Iterable[NamedMetadata], object_type: str) -> dict[str, NamedMetadata]:
    result: dict[str, NamedMetadata] = {}
    duplicates: set[str] = set()
    for item in items:
        name = item.name
        if name in result:
            duplicates.add(name)
        result[name] = item
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise MetadataValidationError(f"duplicate {object_type} definitions: {duplicate_list}")
    return result


def _validate_metadata(
    domains: dict[str, DomainMetadata],
    semantics: dict[str, TableSemanticMetadata],
    physical: dict[str, PhysicalTableMetadata],
) -> None:
    semantic_without_physical = set(semantics).difference(physical)
    if semantic_without_physical:
        raise MetadataValidationError(
            "semantic tables absent from the database: "
            + ", ".join(sorted(semantic_without_physical))
        )

    missing_semantics = set(physical).difference(semantics)
    if missing_semantics:
        raise MetadataValidationError(
            "physical tables missing semantic coverage: " + ", ".join(sorted(missing_semantics))
        )

    for domain in domains.values():
        for table_name in domain.tables:
            if table_name not in physical:
                raise MetadataValidationError(
                    f"domain {domain.name!r} references unknown table {table_name!r}"
                )
            if domain.name not in semantics[table_name].domains:
                raise MetadataValidationError(
                    f"domain mapping mismatch for {domain.name!r} and {table_name!r}"
                )

    for table in semantics.values():
        physical_columns = {column.name for column in physical[table.name].columns}
        unknown_columns = set(table.columns).difference(physical_columns)
        if unknown_columns:
            raise MetadataValidationError(
                f"semantic table {table.name!r} references unknown columns: "
                + ", ".join(sorted(unknown_columns))
            )
        for domain_name in table.domains:
            if domain_name not in domains:
                raise MetadataValidationError(
                    f"table {table.name!r} references unknown domain {domain_name!r}"
                )
            if table.name not in domains[domain_name].tables:
                raise MetadataValidationError(
                    f"domain mapping mismatch for {domain_name!r} and {table.name!r}"
                )

    for table in physical.values():
        source_columns = {column.name for column in table.columns}
        for relationship in table.relationships:
            if relationship.source_table != table.name:
                raise MetadataValidationError(
                    f"relationship source {relationship.source_table!r} does not match "
                    f"table {table.name!r}"
                )
            if not set(relationship.source_columns).issubset(source_columns):
                raise MetadataValidationError(
                    f"relationship on {table.name!r} references unknown source columns"
                )
            if relationship.target_table not in physical:
                raise MetadataValidationError(
                    f"relationship on {table.name!r} references unknown target table "
                    f"{relationship.target_table!r}"
                )
            target_columns = {column.name for column in physical[relationship.target_table].columns}
            if not set(relationship.target_columns).issubset(target_columns):
                raise MetadataValidationError(
                    f"relationship on {table.name!r} references unknown target columns"
                )


def _merge_table(
    physical: PhysicalTableMetadata,
    semantic: TableSemanticMetadata,
) -> TableMetadata:
    columns: list[ColumnMetadata] = []
    for physical_column in sorted(physical.columns, key=lambda item: item.name):
        semantic_column = semantic.columns.get(physical_column.name)
        foreign_keys = sorted(
            f"{relationship.target_table}.{target_column}"
            for relationship in physical.relationships
            for source_column, target_column in zip(
                relationship.source_columns,
                relationship.target_columns,
                strict=True,
            )
            if source_column == physical_column.name
        )
        columns.append(
            ColumnMetadata(
                **physical_column.model_dump(),
                foreign_keys=foreign_keys,
                description=semantic_column.description if semantic_column else None,
                aliases=list(semantic_column.aliases) if semantic_column else [],
                value_hints=(list(semantic_column.value_hints) if semantic_column else []),
                notes=list(semantic_column.notes) if semantic_column else [],
            )
        )
    return TableMetadata(
        name=physical.name,
        description=semantic.description,
        grain=semantic.grain,
        domains=list(semantic.domains),
        aliases=list(semantic.aliases),
        columns=columns,
        relationships=list(physical.relationships),
        unique_constraints=[list(columns) for columns in physical.unique_constraints],
        notes=list(semantic.notes),
    )
