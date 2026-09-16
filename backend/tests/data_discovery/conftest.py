"""Data Discovery fixtures."""

import pytest

from app.data_discovery.loader import load_dataset_registry
from app.data_discovery.models import DatasetRegistration
from app.metadata.model_registry import build_model_metadata_registry


@pytest.fixture
def registrations() -> tuple[DatasetRegistration, ...]:
    return load_dataset_registry(build_model_metadata_registry())
