"""Semantica fixtures."""

from pathlib import Path

import pytest

from app.knowledge_catalog.loader import CatalogHierarchy, CatalogLoader


@pytest.fixture
def catalog_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "knowledge_catalog"


@pytest.fixture
def hierarchy(catalog_root: Path) -> CatalogHierarchy:
    return CatalogLoader(catalog_root).load()
