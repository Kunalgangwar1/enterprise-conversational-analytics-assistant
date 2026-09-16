"""Database-independent metadata fixtures for NLP-to-SQL unit tests."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine

import app.db.models  # noqa: F401
from app.db.base import Base
from app.metadata.introspector import SchemaIntrospector
from app.metadata.loader import load_semantic_metadata
from app.metadata.registry import MetadataRegistry


@pytest.fixture
def metadata_registry() -> Iterator[MetadataRegistry]:
    """Build real metadata contracts over an empty in-memory SQLite schema."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    domains, semantic_tables = load_semantic_metadata()
    physical_tables = SchemaIntrospector(engine, schema=None).inspect()
    yield MetadataRegistry(domains, semantic_tables, physical_tables)
    engine.dispose()
