"""Build the existing MetadataRegistry from local ORM model metadata only."""

from sqlalchemy import UniqueConstraint

import app.db.models  # noqa: F401
from app.db.base import Base
from app.metadata.loader import load_semantic_metadata
from app.metadata.models import PhysicalColumnMetadata, PhysicalTableMetadata, RelationshipMetadata
from app.metadata.registry import MetadataRegistry


def build_model_metadata_registry() -> MetadataRegistry:
    """Compose semantic metadata with SQLAlchemy definitions without opening a database."""

    domains, semantics = load_semantic_metadata()
    physical: list[PhysicalTableMetadata] = []
    for table in Base.metadata.sorted_tables:
        unique_sets = [
            [column.name for column in constraint.columns]
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        relationships = [
            RelationshipMetadata(
                source_table=table.name,
                source_columns=[foreign_key.parent.name],
                target_table=foreign_key.column.table.name,
                target_columns=[foreign_key.column.name],
                constraint_name=foreign_key.constraint.name,
            )
            for foreign_key in table.foreign_keys
        ]
        physical.append(
            PhysicalTableMetadata(
                name=table.name,
                columns=[
                    PhysicalColumnMetadata(
                        name=column.name,
                        data_type=str(column.type),
                        nullable=column.nullable,
                        primary_key=column.primary_key,
                        unique=bool(column.unique),
                    )
                    for column in table.columns
                ],
                relationships=relationships,
                unique_constraints=unique_sets,
            )
        )
    return MetadataRegistry(domains, semantics, physical)
