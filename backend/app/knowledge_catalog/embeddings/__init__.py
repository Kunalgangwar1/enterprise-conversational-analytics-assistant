"""Embedding adapters for Knowledge Catalog vector retrieval."""

from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.embeddings.factory import create_embedding_client, get_embedding_client
from app.knowledge_catalog.embeddings.gemini import GeminiEmbeddingClient

__all__ = [
    "EmbeddingClient",
    "GeminiEmbeddingClient",
    "create_embedding_client",
    "get_embedding_client",
]
