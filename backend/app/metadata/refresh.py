"""Refresh the merged metadata snapshot from semantic config and PostgreSQL."""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from app.core.config import get_settings
from app.db.session import create_database_engine
from app.metadata.exceptions import MetadataError, MetadataRefreshError
from app.metadata.introspector import SchemaIntrospector
from app.metadata.loader import load_semantic_metadata
from app.metadata.models import SchemaMetadata
from app.metadata.registry import MetadataRegistry

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_PATH = _BACKEND_ROOT / "artifacts" / "metadata" / "schema_metadata.json"


def build_registry(engine: Engine) -> MetadataRegistry:
    """Build and validate a registry against the supplied database engine."""

    domains, semantic_tables = load_semantic_metadata()
    physical_tables = SchemaIntrospector(engine).inspect()
    return MetadataRegistry(domains, semantic_tables, physical_tables)


def refresh_metadata(
    engine: Engine,
    output_path: Path = DEFAULT_SNAPSHOT_PATH,
    *,
    generated_at: datetime | None = None,
) -> SchemaMetadata:
    """Validate metadata and atomically write a credential-free JSON snapshot."""

    registry = build_registry(engine)
    snapshot = registry.to_schema_metadata(generated_at=generated_at or datetime.now(UTC))
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(output_path)
    except OSError as exc:
        raise MetadataRefreshError(f"unable to write metadata snapshot to {output_path}") from exc
    return snapshot


def main() -> int:
    """Run the metadata refresh command using the schema-owner database URL."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help="JSON snapshot path",
    )
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    engine = create_database_engine(str(settings.database_url))
    try:
        snapshot = refresh_metadata(engine, args.output)
    except MetadataError as exc:
        logger.error("metadata refresh failed: %s", exc)
        return 1
    finally:
        engine.dispose()

    logger.info(
        "metadata snapshot refreshed: %d domains, %d tables, %s",
        len(snapshot.domains),
        len(snapshot.tables),
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
