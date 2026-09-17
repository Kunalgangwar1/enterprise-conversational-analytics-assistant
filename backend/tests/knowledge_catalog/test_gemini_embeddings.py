"""Network-free Gemini embedding adapter and factory tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors

import app.knowledge_catalog.embeddings.factory as factory
from app.core.config import Settings
from app.knowledge_catalog.embeddings.gemini import GeminiEmbeddingClient
from app.knowledge_catalog.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)
from app.reliability.clients import ResilientEmbeddingClient


def test_gemini_document_and_query_embeddings_use_retrieval_semantics() -> None:
    sdk = MagicMock()
    sdk.models.embed_content.side_effect = [
        SimpleNamespace(
            embeddings=[SimpleNamespace(values=[1.0, 0.0]), SimpleNamespace(values=[0.0, 1.0])]
        ),
        SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 0.0])]),
    ]
    client = GeminiEmbeddingClient(
        api_key="test-key",
        model="gemini-embedding-2",
        dimensions=2,
        sdk_client=sdk,
    )

    documents = client.embed_documents(["first", "second"])
    query = client.embed_query("query")

    assert documents == [[1.0, 0.0], [0.0, 1.0]]
    assert query == [1.0, 0.0]
    calls = sdk.models.embed_content.call_args_list
    assert calls[0].kwargs["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert calls[1].kwargs["config"].task_type == "RETRIEVAL_QUERY"
    assert calls[0].kwargs["config"].output_dimensionality == 2


def test_gemini_embedding_dimension_and_empty_response_validation() -> None:
    sdk = MagicMock()
    sdk.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=[1.0])]
    )
    client = GeminiEmbeddingClient(
        api_key="test-key",
        model="gemini-embedding-2",
        dimensions=2,
        sdk_client=sdk,
    )

    with pytest.raises(EmbeddingProviderError, match="dimensions"):
        client.embed_query("query")


def test_embedding_factory_selects_gemini_and_retains_azure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gemini_constructor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(factory, "GeminiEmbeddingClient", gemini_constructor)
    factory.create_embedding_client(Settings(_env_file=None, gemini_api_key="test-key"))
    gemini_constructor.assert_called_once()

    azure = factory.create_embedding_client(
        Settings(
            _env_file=None,
            embedding_provider="azure_openai",
            azure_openai_endpoint="https://example.openai.azure.com/",
            azure_openai_api_key="test-key",
            azure_openai_embedding_deployment="embedding-deployment",
        )
    )
    assert isinstance(azure, ResilientEmbeddingClient)
    assert azure.provider_name == "azure_openai"


def test_missing_key_and_provider_error_are_safe() -> None:
    with pytest.raises(EmbeddingConfigurationError, match="GEMINI_API_KEY"):
        factory.create_embedding_client(Settings(_env_file=None))

    sdk = MagicMock()
    sdk.models.embed_content.side_effect = errors.ClientError(401, {"message": "private-test-key"})
    client = GeminiEmbeddingClient(
        api_key="private-test-key",
        model="gemini-embedding-2",
        dimensions=2,
        sdk_client=sdk,
    )
    with pytest.raises(EmbeddingAuthenticationError) as exc_info:
        client.embed_query("safe query")
    assert "private-test-key" not in str(exc_info.value)
