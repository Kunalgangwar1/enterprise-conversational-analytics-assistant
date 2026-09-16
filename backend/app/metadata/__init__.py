"""Physical and semantic schema metadata services."""

from app.metadata.introspector import SchemaIntrospector
from app.metadata.loader import load_semantic_metadata
from app.metadata.registry import MetadataRegistry

__all__ = ["MetadataRegistry", "SchemaIntrospector", "load_semantic_metadata"]
