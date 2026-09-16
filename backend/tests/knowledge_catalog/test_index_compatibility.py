"""Embedding manifest compatibility and rebuild tests."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.knowledge_catalog.exceptions import EmbeddingIndexMismatchError
from app.knowledge_catalog.hybrid_retriever import HybridCatalogRetriever
from app.knowledge_catalog.index import build_index
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from tests.knowledge_catalog.fakes import FakeEmbeddingClient


class ConfigurableFakeEmbeddingClient(FakeEmbeddingClient):
    def __init__(self, *, provider: str, model: str, dimensions: int) -> None:
        super().__init__(dimensions=dimensions)
        self.provider_name = provider
        self.model_name = model


def test_matching_manifest_is_accepted_and_records_model(
    catalog_settings: Settings,
    tmp_path: Path,
) -> None:
    client = ConfigurableFakeEmbeddingClient(provider="gemini", model="gemini-test", dimensions=8)
    index_dir = tmp_path / "index" / "lancedb"
    manifest = build_index(
        settings=catalog_settings,
        embedding_client=client,
        index_dir=index_dir,
    )

    loaded = LanceDBKnowledgeStore(index_dir).validate_compatibility(client)

    assert manifest.embedding_provider == loaded.embedding_provider == "gemini"
    assert manifest.embedding_model == loaded.embedding_model == "gemini-test"
    assert manifest.embedding_dimensions == loaded.embedding_dimensions == 8


@pytest.mark.parametrize(
    "current",
    [
        ConfigurableFakeEmbeddingClient(provider="gemini", model="same-model", dimensions=8),
        ConfigurableFakeEmbeddingClient(provider="azure_openai", model="same-model", dimensions=4),
    ],
)
def test_mismatch_stops_before_embedding_or_vector_search(
    catalog_settings: Settings,
    tmp_path: Path,
    current: ConfigurableFakeEmbeddingClient,
) -> None:
    built_with = ConfigurableFakeEmbeddingClient(
        provider="azure_openai", model="same-model", dimensions=8
    )
    index_dir = tmp_path / "index" / "lancedb"
    build_index(settings=catalog_settings, embedding_client=built_with, index_dir=index_dir)
    store = LanceDBKnowledgeStore(index_dir)
    store.search_hybrid = MagicMock()  # type: ignore[method-assign]
    retriever = HybridCatalogRetriever(
        store=store,
        embedding_client_factory=lambda: current,
        top_k=3,
    )

    with pytest.raises(EmbeddingIndexMismatchError, match="mismatch"):
        retriever.retrieve("claims")

    assert current.query_calls == []
    store.search_hybrid.assert_not_called()


def test_rebuild_updates_manifest_to_current_embedding_config(
    catalog_settings: Settings,
    tmp_path: Path,
) -> None:
    index_dir = tmp_path / "index" / "lancedb"
    azure = ConfigurableFakeEmbeddingClient(provider="azure_openai", model="azure", dimensions=6)
    gemini = ConfigurableFakeEmbeddingClient(provider="gemini", model="gemini", dimensions=10)
    build_index(settings=catalog_settings, embedding_client=azure, index_dir=index_dir)

    rebuilt = build_index(settings=catalog_settings, embedding_client=gemini, index_dir=index_dir)

    assert rebuilt.embedding_provider == "gemini"
    assert rebuilt.embedding_model == "gemini"
    assert rebuilt.embedding_dimensions == 10
    LanceDBKnowledgeStore(index_dir).validate_compatibility(gemini)
