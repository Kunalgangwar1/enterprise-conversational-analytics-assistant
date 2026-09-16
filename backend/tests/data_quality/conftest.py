"""Data Quality fixtures."""

from pathlib import Path

import pytest

from app.data_quality.loader import DataQualityLoader
from app.data_quality.models import DataQualityDocument


@pytest.fixture
def dq_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "data_quality"


@pytest.fixture
def dq_documents(dq_root: Path) -> tuple[DataQualityDocument, ...]:
    return DataQualityLoader(dq_root).load()
