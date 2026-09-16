"""Read physical schema metadata through SQLAlchemy's public inspection API."""

from collections.abc import Collection

from sqlalchemy import Engine, inspect
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.exc import SQLAlchemyError

from app.metadata.constants import (
    DEFAULT_DATABASE_SCHEMA,
    EXPECTED_APPLICATION_TABLES,
)
from app.metadata.exceptions import MetadataIntrospectionError
from app.metadata.models import (
    PhysicalColumnMetadata,
    PhysicalTableMetadata,
    RelationshipMetadata,
)


class SchemaIntrospector:
    """Inspect only the application's known tables; never inspect row data."""

    def __init__(
        self,
        engine: Engine,
        *,
        schema: str | None = DEFAULT_DATABASE_SCHEMA,
        expected_tables: Collection[str] = EXPECTED_APPLICATION_TABLES,
    ) -> None:
        self._engine = engine
        self._schema = schema
        self._expected_tables = frozenset(expected_tables)

    def inspect(self) -> tuple[PhysicalTableMetadata, ...]:
        """Return deterministic physical metadata for known application tables."""

        try:
            inspector = inspect(self._engine)
            present_tables = self._expected_tables.intersection(
                inspector.get_table_names(schema=self._schema)
            )
            return tuple(
                self._inspect_table(inspector, table_name) for table_name in sorted(present_tables)
            )
        except SQLAlchemyError as exc:
            raise MetadataIntrospectionError(
                "unable to inspect application database metadata"
            ) from exc

    def _inspect_table(self, inspector: Inspector, table_name: str) -> PhysicalTableMetadata:
        primary_key = inspector.get_pk_constraint(table_name, schema=self._schema)
        primary_key_columns = frozenset(primary_key.get("constrained_columns") or ())

        unique_constraints = {
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints(table_name, schema=self._schema)
            if constraint.get("column_names")
        }
        for index in inspector.get_indexes(table_name, schema=self._schema):
            if index.get("unique") and index.get("column_names"):
                unique_constraints.add(tuple(index["column_names"]))

        unique_columns = {columns[0] for columns in unique_constraints if len(columns) == 1}
        columns = tuple(
            PhysicalColumnMetadata(
                name=column["name"],
                data_type=str(column["type"]),
                nullable=bool(column["nullable"]),
                primary_key=column["name"] in primary_key_columns,
                unique=column["name"] in unique_columns,
            )
            for column in inspector.get_columns(table_name, schema=self._schema)
        )

        relationships = tuple(
            sorted(
                (
                    RelationshipMetadata(
                        source_table=table_name,
                        source_columns=foreign_key["constrained_columns"],
                        target_table=foreign_key["referred_table"],
                        target_columns=foreign_key["referred_columns"],
                        constraint_name=foreign_key.get("name"),
                    )
                    for foreign_key in inspector.get_foreign_keys(table_name, schema=self._schema)
                    if foreign_key.get("referred_table") in self._expected_tables
                ),
                key=lambda item: (
                    item.source_columns,
                    item.target_table,
                    item.target_columns,
                ),
            )
        )

        return PhysicalTableMetadata(
            name=table_name,
            columns=list(columns),
            relationships=list(relationships),
            unique_constraints=[list(columns) for columns in sorted(unique_constraints)],
        )
