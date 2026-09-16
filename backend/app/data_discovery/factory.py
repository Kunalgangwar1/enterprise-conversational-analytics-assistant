"""Composition for deterministic Data Discovery."""

from app.core.config import Settings
from app.data_discovery.loader import load_dataset_registry
from app.data_discovery.search import DataDiscoveryService
from app.metadata.model_registry import build_model_metadata_registry


def build_data_discovery_service(settings: Settings) -> DataDiscoveryService:
    registry = build_model_metadata_registry()
    return DataDiscoveryService(
        load_dataset_registry(registry),
        top_k=settings.data_discovery_top_k,
    )
