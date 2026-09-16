"""PostgreSQL integration tests for the Phase 5 metadata subsystem."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import create_database_engine
from app.metadata.constants import EXPECTED_APPLICATION_TABLES
from app.metadata.introspector import SchemaIntrospector
from app.metadata.refresh import build_registry, refresh_metadata

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def metadata_engine() -> Iterator[Engine]:
    settings = get_settings()
    engine = create_database_engine(str(settings.database_url))
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Could not connect to the configured PostgreSQL DATABASE_URL")

    yield engine
    engine.dispose()


def test_postgresql_introspection_and_registry_merge(metadata_engine: Engine) -> None:
    physical = SchemaIntrospector(metadata_engine).inspect()
    registry = build_registry(metadata_engine)

    physical_by_name = {table.name: table for table in physical}
    claims = physical_by_name["claims"]
    claims_columns = {column.name for column in claims.columns}

    assert {table.name for table in physical} == set(EXPECTED_APPLICATION_TABLES)
    assert {"provider_id", "claim_status", "submitted_amount"}.issubset(claims_columns)
    assert any(
        relationship.source_columns == ["provider_id"]
        and relationship.target_table == "providers"
        and relationship.target_columns == ["id"]
        for relationship in claims.relationships
    )
    assert len(registry.list_domains()) == 5
    assert len(registry.list_tables()) == 7
    assert any(
        relationship.target_table == "claims"
        for relationship in registry.get_relationships("claim_lines")
    )


def test_refresh_writes_valid_snapshot_to_temporary_path(
    metadata_engine: Engine,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "schema_metadata.json"
    generated_at = datetime(2026, 1, 1, tzinfo=UTC)

    snapshot = refresh_metadata(
        metadata_engine,
        output_path,
        generated_at=generated_at,
    )

    assert output_path.exists()
    assert snapshot.generated_at == generated_at
    payload = output_path.read_text(encoding="utf-8")
    assert '"metadata_version": "1.0"' in payload
    assert "postgresql://" not in payload
    assert "DATABASE_URL" not in payload
