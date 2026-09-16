"""Unit tests for introspection, registry validation, and context generation."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine

import app.db.models  # noqa: F401
from app.db.base import Base
from app.metadata.exceptions import MetadataValidationError
from app.metadata.introspector import SchemaIntrospector
from app.metadata.loader import load_semantic_metadata
from app.metadata.models import DomainMetadata, TableSemanticMetadata
from app.metadata.registry import MetadataRegistry


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def registry(sqlite_engine: Engine) -> MetadataRegistry:
    domains, semantics = load_semantic_metadata()
    physical = SchemaIntrospector(sqlite_engine, schema=None).inspect()
    return MetadataRegistry(domains, semantics, physical)


def test_introspector_collects_known_tables_columns_keys_and_uniques(
    sqlite_engine: Engine,
) -> None:
    tables = {
        table.name: table for table in SchemaIntrospector(sqlite_engine, schema=None).inspect()
    }

    assert len(tables) == 7
    assert {column.name for column in tables["claims"].columns} >= {
        "id",
        "claim_status",
        "submitted_amount",
    }
    assert next(column for column in tables["claims"].columns if column.name == "id").primary_key
    assert ["claim_external_id"] in tables["claims"].unique_constraints
    assert any(
        relationship.target_table == "claims"
        for relationship in tables["claim_lines"].relationships
    )


def test_registry_supports_required_lookups(registry: MetadataRegistry) -> None:
    assert len(registry.list_domains()) == 5
    assert len(registry.list_tables()) == 7
    assert registry.get_domain("claims").description
    assert registry.get_table("claim_lines").grain.startswith("One row per service line")
    assert [table.name for table in registry.tables_for_domain("provider_network")] == [
        "facilities",
        "providers",
    ]
    assert any(
        relationship.target_table == "facilities"
        for relationship in registry.get_relationships("providers")
    )


def test_registry_rejects_semantic_column_absent_from_database(
    sqlite_engine: Engine,
) -> None:
    domains, semantics = load_semantic_metadata()
    physical = SchemaIntrospector(sqlite_engine, schema=None).inspect()
    members = next(table for table in semantics if table.name == "members")
    example_column = next(iter(members.columns.values()))
    invalid_members = members.model_copy(
        update={"columns": {**members.columns, "missing_column": example_column}}
    )
    invalid_semantics = tuple(
        invalid_members if table.name == "members" else table for table in semantics
    )

    with pytest.raises(MetadataValidationError, match="unknown columns"):
        MetadataRegistry(domains, invalid_semantics, physical)


def test_registry_rejects_semantic_table_absent_from_database(
    sqlite_engine: Engine,
) -> None:
    domains, semantics = load_semantic_metadata()
    physical = SchemaIntrospector(sqlite_engine, schema=None).inspect()
    invalid_table = TableSemanticMetadata(
        name="missing_table",
        description="Invalid test-only table.",
        grain="One row per invalid record.",
        domains=["member"],
    )

    with pytest.raises(MetadataValidationError, match="absent from the database"):
        MetadataRegistry(domains, (*semantics, invalid_table), physical)


def test_registry_rejects_invalid_domain_table_reference(sqlite_engine: Engine) -> None:
    domains, semantics = load_semantic_metadata()
    physical = SchemaIntrospector(sqlite_engine, schema=None).inspect()
    invalid_domain = DomainMetadata(
        name="invalid",
        description="Invalid test-only domain.",
        tables=["missing_table"],
    )

    with pytest.raises(MetadataValidationError, match="unknown table"):
        MetadataRegistry((*domains, invalid_domain), semantics, physical)


def test_registry_rejects_inconsistent_domain_mapping(sqlite_engine: Engine) -> None:
    domains, semantics = load_semantic_metadata()
    physical = SchemaIntrospector(sqlite_engine, schema=None).inspect()
    members = next(table for table in semantics if table.name == "members")
    invalid_members = TableSemanticMetadata(**{**members.model_dump(), "domains": ["claims"]})
    invalid_semantics = tuple(
        invalid_members if table.name == "members" else table for table in semantics
    )

    with pytest.raises(MetadataValidationError, match="domain mapping mismatch"):
        MetadataRegistry(domains, invalid_semantics, physical)


def test_context_contains_only_selected_tables_and_relationships(
    registry: MetadataRegistry,
) -> None:
    context = registry.build_context(["providers", "claims", "facilities"])

    assert "TABLE claims" in context
    assert "TABLE facilities" in context
    assert "TABLE providers" in context
    assert "TABLE members" not in context
    assert "providers.facility_id -> facilities.id" in context
    assert "Value hints: submitted, pending, paid, denied, adjusted" in context


def test_context_is_deterministic_and_deduplicates_selection(
    registry: MetadataRegistry,
) -> None:
    first = registry.build_context(["providers", "claims", "providers"])
    second = registry.build_context(["claims", "providers"])

    assert first == second
    assert first.index("TABLE claims") < first.index("TABLE providers")
