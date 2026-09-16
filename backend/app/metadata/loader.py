"""Load and validate business-semantic metadata from YAML configuration."""

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from app.metadata.exceptions import MetadataConfigurationError
from app.metadata.models import (
    DomainCatalog,
    DomainMetadata,
    TableCatalog,
    TableSemanticMetadata,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA_CONFIG_DIRECTORY = _BACKEND_ROOT / "config" / "metadata"
DEFAULT_DOMAINS_PATH = DEFAULT_METADATA_CONFIG_DIRECTORY / "domains.yaml"
DEFAULT_TABLES_PATH = DEFAULT_METADATA_CONFIG_DIRECTORY / "tables.yaml"

CatalogModel = TypeVar("CatalogModel", bound=BaseModel)


def load_domains(path: Path = DEFAULT_DOMAINS_PATH) -> tuple[DomainMetadata, ...]:
    """Load domain definitions from a YAML file."""

    return tuple(_load_catalog(path, DomainCatalog).domains)


def load_tables(path: Path = DEFAULT_TABLES_PATH) -> tuple[TableSemanticMetadata, ...]:
    """Load table semantic definitions from a YAML file."""

    return tuple(_load_catalog(path, TableCatalog).tables)


def load_semantic_metadata(
    domains_path: Path = DEFAULT_DOMAINS_PATH,
    tables_path: Path = DEFAULT_TABLES_PATH,
) -> tuple[tuple[DomainMetadata, ...], tuple[TableSemanticMetadata, ...]]:
    """Load both semantic metadata catalogs."""

    return load_domains(domains_path), load_tables(tables_path)


def _load_catalog(path: Path, model: type[CatalogModel]) -> CatalogModel:
    try:
        with path.open(encoding="utf-8") as stream:
            raw_catalog = yaml.safe_load(stream)
    except FileNotFoundError as exc:
        raise MetadataConfigurationError(
            f"metadata configuration file does not exist: {path}"
        ) from exc
    except (OSError, yaml.YAMLError) as exc:
        raise MetadataConfigurationError(
            f"unable to read metadata configuration file {path}: {exc}"
        ) from exc

    try:
        return model.model_validate(raw_catalog)
    except ValidationError as exc:
        raise MetadataConfigurationError(
            f"invalid metadata configuration in {path}: {exc}"
        ) from exc
