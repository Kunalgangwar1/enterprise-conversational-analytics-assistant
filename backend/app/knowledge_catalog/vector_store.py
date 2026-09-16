"""Reusable local LanceDB storage with index-embedding compatibility checks."""

import json
from pathlib import Path
from typing import Any

import lancedb
from lancedb.index import FTS
from lancedb.rerankers import RRFReranker
from pydantic import ValidationError

from app.knowledge_catalog.embeddings.base import EmbeddingClient
from app.knowledge_catalog.exceptions import (
    EmbeddingIndexMismatchError,
    KnowledgeIndexError,
    KnowledgeIndexUnavailableError,
)
from app.knowledge_catalog.models import (
    CatalogChunk,
    IndexManifest,
    KnowledgeEvidence,
    RetrievalMethod,
)

_TABLE_NAME = "knowledge_chunks"


class LanceDBKnowledgeStore:
    """Adapt LanceDB rows into the common KnowledgeEvidence model."""

    def __init__(
        self,
        index_dir: Path,
        *,
        table_name: str = _TABLE_NAME,
        retrieval_method: RetrievalMethod = RetrievalMethod.HYBRID,
        manifest_path: Path | None = None,
    ) -> None:
        self.index_dir = index_dir
        self._table_name = table_name
        self._retrieval_method = retrieval_method
        self._manifest_path = manifest_path or index_dir.parent / "index_manifest.json"

    def rebuild(self, chunks: tuple[CatalogChunk, ...], vectors: list[list[float]]) -> None:
        if not chunks:
            raise KnowledgeIndexError("Cannot build a Knowledge Catalog index with no chunks")
        if len(chunks) != len(vectors):
            raise KnowledgeIndexError("Chunk and embedding counts do not match")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or 0 in dimensions:
            raise KnowledgeIndexError("Embedding vectors must have one non-zero dimension")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                **chunk.model_dump(mode="json"),
                "node_type": chunk.node_type.value,
                "domain": chunk.domain or "",
                "vector": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        try:
            table = lancedb.connect(self.index_dir).create_table(
                self._table_name, data=rows, mode="overwrite"
            )
            table.create_index("text", config=FTS(), replace=True)
        except Exception as exc:
            raise KnowledgeIndexError("Unable to build local LanceDB catalog index") from exc

    def count(self) -> int:
        return self._table().count_rows()

    def list_index_types(self) -> tuple[str, ...]:
        return tuple(index.index_type for index in self._table().list_indices())

    def validate_compatibility(
        self,
        client: EmbeddingClient,
        *,
        actual_dimensions: int | None = None,
    ) -> IndexManifest:
        """Fail before search when provider, model, or dimensions differ."""

        try:
            manifest = IndexManifest.model_validate_json(
                self._manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError) as exc:
            raise EmbeddingIndexMismatchError(
                "Vector index manifest is missing or invalid; rebuild the managed index"
            ) from exc
        expected_dimensions = actual_dimensions or client.dimensions
        mismatches: list[str] = []
        if manifest.embedding_provider != client.provider_name:
            mismatches.append("provider")
        if manifest.resolved_embedding_model != client.model_name:
            mismatches.append("model")
        if expected_dimensions is not None and manifest.embedding_dimensions != expected_dimensions:
            mismatches.append("dimensions")
        if mismatches:
            raise EmbeddingIndexMismatchError(
                "Vector index embedding configuration mismatch "
                f"({', '.join(mismatches)}); rebuild the managed index"
            )
        return manifest

    def search_vector(
        self, query_vector: list[float], *, limit: int
    ) -> tuple[KnowledgeEvidence, ...]:
        try:
            rows = self._table().search(query_vector, query_type="vector").limit(limit).to_list()
        except Exception as exc:
            raise KnowledgeIndexError("LanceDB vector search failed") from exc
        return _rows_to_evidence(rows, limit, self._retrieval_method)

    def search_fts(self, query: str, *, limit: int) -> tuple[KnowledgeEvidence, ...]:
        try:
            rows = self._table().search(query, query_type="fts").limit(limit).to_list()
        except Exception as exc:
            raise KnowledgeIndexError("LanceDB full-text search failed") from exc
        return _rows_to_evidence(rows, limit, self._retrieval_method)

    def search_hybrid(
        self, query: str, query_vector: list[float], *, limit: int
    ) -> tuple[KnowledgeEvidence, ...]:
        try:
            rows = (
                self._table()
                .search(query_type="hybrid")
                .vector(query_vector)
                .text(query)
                .rerank(RRFReranker())
                .limit(limit)
                .to_list()
            )
        except Exception as exc:
            raise KnowledgeIndexError("LanceDB hybrid search failed") from exc
        return _rows_to_evidence(rows, limit, self._retrieval_method)

    def all_evidence(self) -> tuple[KnowledgeEvidence, ...]:
        """Return indexed metadata/text without exposing stored vectors."""

        try:
            rows = self._table().to_arrow().to_pylist()
        except Exception as exc:
            raise KnowledgeIndexError("Unable to read indexed catalog chunks") from exc
        ordered = sorted(rows, key=lambda row: str(row["chunk_id"]))
        return _rows_to_evidence(ordered, len(ordered), self._retrieval_method)

    def _table(self):
        try:
            database = lancedb.connect(self.index_dir)
            if self._table_name not in database.list_tables().tables:
                raise KnowledgeIndexUnavailableError(
                    "Knowledge Catalog index is not built; run the catalog index command"
                )
            return database.open_table(self._table_name)
        except KnowledgeIndexUnavailableError:
            raise
        except Exception as exc:
            raise KnowledgeIndexError("Unable to open local LanceDB catalog index") from exc


def _rows_to_evidence(
    rows: list[dict[str, Any]],
    limit: int,
    retrieval_method: RetrievalMethod,
) -> tuple[KnowledgeEvidence, ...]:
    evidence: list[KnowledgeEvidence] = []
    for rank, row in enumerate(rows[:limit], start=1):
        raw_score = row.get("_relevance_score", row.get("_score"))
        score = float(raw_score) if isinstance(raw_score, int | float) else None
        evidence.append(
            KnowledgeEvidence(
                evidence_id=str(row["chunk_id"]),
                chunk_id=str(row["chunk_id"]),
                node_id=str(row["node_id"]),
                title=str(row["title"]),
                section=str(row["section"]),
                source_path=str(row["source_path"]),
                text=str(row["text"]),
                retrieval_method=retrieval_method,
                rank=rank,
                score=score,
            )
        )
    return tuple(evidence)
