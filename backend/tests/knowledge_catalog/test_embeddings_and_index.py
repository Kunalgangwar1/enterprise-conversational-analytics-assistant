"""Embedding abstraction and temporary LanceDB tests."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.knowledge_catalog.embeddings.azure_openai import AzureOpenAIEmbeddingClient
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.exceptions import EmbeddingConfigurationError
from app.knowledge_catalog.index import build_index
from app.knowledge_catalog.models import KnowledgeEvidence
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.main import create_app
from tests.knowledge_catalog.fakes import FakeEmbeddingClient


def test_fake_embeddings_are_deterministic_and_dimensionally_consistent() -> None:
    fake = FakeEmbeddingClient(dimensions=12)

    documents = fake.embed_documents(["claims allowed amount", "appointments"])
    query = fake.embed_query("claims allowed amount")

    assert documents[0] == query
    assert {len(vector) for vector in [*documents, query]} == {12}


def test_azure_embedding_adapter_uses_injected_sdk_without_network() -> None:
    sdk = _FakeSDK()
    client = AzureOpenAIEmbeddingClient(
        endpoint="https://example.openai.azure.com/",
        api_key="test-key",
        deployment="embedding-test",
        dimensions=3,
        sdk_client=sdk,
    )

    assert client.embed_query("safe text") == [1.0, 0.0, 0.0]
    assert sdk.calls == [{"model": "embedding-test", "input": ["safe text"], "dimensions": 3}]


def test_missing_embedding_config_fails_only_when_factory_is_called(
    catalog_settings: Settings,
) -> None:
    application = create_app(catalog_settings)

    assert application.state.knowledge_catalog_agent is None
    with pytest.raises(EmbeddingConfigurationError, match="EMBEDDING_DEPLOYMENT"):
        create_embedding_client(catalog_settings)


def test_temporary_lancedb_index_supports_fts_vector_and_hybrid(
    catalog_settings: Settings,
    tmp_path: Path,
) -> None:
    fake = FakeEmbeddingClient()
    index_dir = tmp_path / "isolated" / "lancedb"

    first_manifest = build_index(
        settings=catalog_settings,
        embedding_client=fake,
        index_dir=index_dir,
    )
    second_manifest = build_index(
        settings=catalog_settings,
        embedding_client=fake,
        index_dir=index_dir,
    )
    store = LanceDBKnowledgeStore(index_dir)

    assert index_dir != catalog_settings.artifacts_output_dir / "knowledge_catalog" / "lancedb"
    assert first_manifest.chunk_count == second_manifest.chunk_count == store.count()
    assert first_manifest.corpus_hash == second_manifest.corpus_hash
    assert "FTS" in store.list_index_types()

    fts = store.search_fts("allowed_amount", limit=4)
    vector = store.search_vector(fake.embed_query("reimbursement eligible"), limit=4)
    hybrid = store.search_hybrid(
        "allowed amount claim",
        fake.embed_query("reimbursement eligible claim"),
        limit=3,
    )

    assert fts and any(item.node_id in {"dataset_claims", "dataset_claim_lines"} for item in fts)
    assert vector and any("claim" in item.node_id for item in vector)
    assert 0 < len(hybrid) <= 3
    assert all(isinstance(item, KnowledgeEvidence) for item in hybrid)
    assert all(item.retrieval_method == "hybrid" for item in hybrid)
    assert (index_dir.parent / "index_manifest.json").is_file()


class _FakeEmbeddingsAPI:
    def __init__(self, owner: "_FakeSDK") -> None:
        self._owner = owner

    def create(self, **parameters: object) -> SimpleNamespace:
        self._owner.calls.append(parameters)
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0, 0.0, 0.0])])


class _FakeSDK:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.embeddings = _FakeEmbeddingsAPI(self)
