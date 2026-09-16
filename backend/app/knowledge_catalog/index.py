"""Build the deterministic local LanceDB Knowledge Catalog index."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.knowledge_catalog.chunker import CatalogChunker
from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.loader import CatalogLoader
from app.knowledge_catalog.models import CatalogChunk, IndexManifest
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore


def build_index(
    *,
    settings: Settings,
    embedding_client: EmbeddingClient | None = None,
    index_dir: Path | None = None,
) -> IndexManifest:
    """Validate, chunk, embed, and fully rebuild a local catalog index."""

    hierarchy = CatalogLoader(settings.knowledge_catalog_dir).load()
    chunks = CatalogChunker(
        chunk_size_chars=settings.knowledge_chunk_size_chars,
        overlap_chars=settings.knowledge_chunk_overlap_chars,
    ).chunk_hierarchy(hierarchy)
    client = embedding_client or create_embedding_client(settings)
    vectors = client.embed_documents([chunk.text for chunk in chunks])
    store_dir = index_dir or settings.artifacts_output_dir / "knowledge_catalog" / "lancedb"
    LanceDBKnowledgeStore(store_dir).rebuild(chunks, vectors)
    dimensions = len(vectors[0])
    manifest = IndexManifest(
        document_count=len(hierarchy.leaf_documents),
        chunk_count=len(chunks),
        embedding_provider=client.provider_name,
        embedding_model=client.model_name,
        embedding_deployment=client.model_name,
        embedding_dimensions=dimensions,
        corpus_hash=_corpus_hash(chunks),
        built_at=datetime.now(UTC).isoformat(),
    )
    _write_manifest(store_dir.parent / "index_manifest.json", manifest)
    return manifest


def _corpus_hash(chunks: tuple[CatalogChunk, ...]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.model_dump_json().encode("utf-8"))
    return digest.hexdigest()


def _write_manifest(path: Path, manifest: IndexManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    manifest = build_index(settings=get_settings())
    print(
        f"Built Knowledge Catalog index: {manifest.document_count} documents, "
        f"{manifest.chunk_count} chunks, {manifest.embedding_dimensions} dimensions."
    )


if __name__ == "__main__":
    main()
