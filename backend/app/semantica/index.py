"""Build Semantica vectors, adjacency, and a safe manifest."""

from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.index import _corpus_hash, _write_manifest
from app.knowledge_catalog.loader import CatalogLoader
from app.knowledge_catalog.models import IndexManifest, RetrievalMethod
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.semantica.chunker import SemanticaChunker
from app.semantica.graph import build_adjacency, write_graph


def build_semantica_index(
    *,
    settings: Settings,
    embedding_client: EmbeddingClient | None = None,
    artifact_dir: Path | None = None,
) -> tuple[IndexManifest, int]:
    hierarchy = CatalogLoader(settings.knowledge_catalog_dir).load()
    chunks = SemanticaChunker(
        chunk_size_chars=settings.semantica_chunk_size_chars,
        overlap_chars=settings.semantica_chunk_overlap_chars,
    ).chunk_hierarchy(hierarchy)
    client = embedding_client or create_embedding_client(settings)
    vectors = client.embed_documents([chunk.text for chunk in chunks])
    root = artifact_dir or settings.artifacts_output_dir / "semantica"
    store = LanceDBKnowledgeStore(
        root / "lancedb",
        table_name="semantica_chunks",
        retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
        manifest_path=root / "index_manifest.json",
    )
    store.rebuild(chunks, vectors)
    graph = build_adjacency(chunks, hierarchy)
    write_graph(root / "adjacency.json", graph)
    manifest = IndexManifest(
        document_count=len(hierarchy.leaf_documents),
        chunk_count=len(chunks),
        embedding_provider=client.provider_name,
        embedding_model=client.model_name,
        embedding_deployment=client.model_name,
        embedding_dimensions=len(vectors[0]),
        corpus_hash=_corpus_hash(chunks),
        built_at=datetime.now(UTC).isoformat(),
    )
    _write_manifest(root / "index_manifest.json", manifest)
    edge_count = sum(len(neighbors) for neighbors in graph.adjacency.values()) // 2
    return manifest, edge_count


def main() -> None:
    manifest, edge_count = build_semantica_index(settings=get_settings())
    print(
        f"Built Semantica index: {manifest.chunk_count} chunks, "
        f"{edge_count} edges, {manifest.embedding_dimensions} dimensions."
    )


if __name__ == "__main__":
    main()
