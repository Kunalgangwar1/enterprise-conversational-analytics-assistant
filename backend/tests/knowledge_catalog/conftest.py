"""Shared Knowledge Catalog fixtures."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.knowledge_catalog.loader import CatalogHierarchy, CatalogLoader


@pytest.fixture
def catalog_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "knowledge_catalog"


@pytest.fixture
def hierarchy(catalog_root: Path) -> CatalogHierarchy:
    return CatalogLoader(catalog_root).load()


@pytest.fixture
def catalog_settings(catalog_root: Path, tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        knowledge_catalog_dir=catalog_root,
        artifacts_output_dir=tmp_path / "artifacts",
        embedding_provider="azure_openai",
        azure_openai_endpoint=None,
        azure_openai_api_key=None,
        azure_openai_embedding_deployment=None,
    )
