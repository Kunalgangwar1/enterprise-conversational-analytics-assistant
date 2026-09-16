"""Dedicated deterministic 900/120-style Semantica chunking."""

import hashlib

from app.knowledge_catalog.chunker import CatalogChunker
from app.knowledge_catalog.loader import CatalogHierarchy
from app.knowledge_catalog.models import CatalogChunk


class SemanticaChunker:
    """Reuse Markdown boundary logic while retaining independent settings and IDs."""

    def __init__(self, *, chunk_size_chars: int, overlap_chars: int) -> None:
        self.chunk_size_chars = chunk_size_chars
        self.overlap_chars = overlap_chars
        self._chunker = CatalogChunker(
            chunk_size_chars=chunk_size_chars,
            overlap_chars=overlap_chars,
            minimum_chunk_size_chars=1,
        )

    def chunk_hierarchy(self, hierarchy: CatalogHierarchy) -> tuple[CatalogChunk, ...]:
        chunks = self._chunker.chunk_hierarchy(hierarchy)
        return tuple(
            chunk.model_copy(
                update={
                    "chunk_id": "sem_"
                    + hashlib.sha256(f"semantica:{chunk.chunk_id}".encode()).hexdigest()[:16]
                }
            )
            for chunk in chunks
        )
