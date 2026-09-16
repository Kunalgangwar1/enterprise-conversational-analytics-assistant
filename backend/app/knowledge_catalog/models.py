"""Typed models shared across Knowledge Catalog strategies."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CatalogModel(BaseModel):
    """Strict immutable base for catalog values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogNodeType(StrEnum):
    ROOT = "root"
    DOMAIN = "domain"
    DATASET = "dataset"
    POLICY = "policy"
    LINEAGE = "lineage"


class RetrievalMethod(StrEnum):
    HIERARCHICAL = "hierarchical"
    HYBRID = "hybrid"
    NONE = "none"
    SEMANTICA_GRAPH = "semantica_graph"


class CatalogNode(CatalogModel):
    """Explicit hierarchy metadata for one Markdown document."""

    id: NonBlankString
    title: NonBlankString
    node_type: CatalogNodeType
    summary: NonBlankString
    children: tuple[NonBlankString, ...] = ()
    parent: NonBlankString | None = None
    domain: NonBlankString | None = None
    source_path: NonBlankString


class CatalogDocument(CatalogModel):
    """Validated node plus its Markdown body."""

    node: CatalogNode
    text: NonBlankString


class CatalogChunk(CatalogModel):
    """Deterministic vector-index unit derived from a leaf document."""

    chunk_id: NonBlankString
    node_id: NonBlankString
    title: NonBlankString
    section: NonBlankString
    source_path: NonBlankString
    node_type: CatalogNodeType
    domain: str | None = None
    text: NonBlankString


class KnowledgeEvidence(CatalogModel):
    """Provider-independent evidence returned by either retrieval path."""

    evidence_id: NonBlankString
    node_id: NonBlankString
    chunk_id: str | None = None
    title: NonBlankString
    section: NonBlankString
    source_path: NonBlankString
    text: NonBlankString
    retrieval_method: RetrievalMethod
    rank: int = Field(ge=1)
    score: float | None = None
    graph_distance: int | None = Field(default=None, ge=0, le=2)
    seed_rank: int | None = Field(default=None, ge=1)


class RetrievalResult(CatalogModel):
    """Bounded evidence and strategy outcome."""

    evidence: tuple[KnowledgeEvidence, ...] = ()
    retrieval_method: RetrievalMethod
    sufficient: bool
    confidence: float | None = Field(default=None, ge=0, le=1)


class CatalogTraversalDecision(CatalogModel):
    """Small structured hierarchy routing decision without model reasoning."""

    selected_child_ids: list[NonBlankString]
    confidence: float = Field(ge=0, le=1)


class GroundedCatalogAnswer(CatalogModel):
    """Structured answer whose citations are validated after generation."""

    answer: NonBlankString
    citation_ids: list[NonBlankString]

    @model_validator(mode="after")
    def require_unique_citations(self) -> Self:
        if len(self.citation_ids) != len(set(self.citation_ids)):
            raise ValueError("citation_ids must be unique")
        return self


class KnowledgeCitation(CatalogModel):
    """Safe provenance returned over the specialist API."""

    id: NonBlankString
    title: NonBlankString
    section: NonBlankString
    source_path: NonBlankString


class KnowledgeCatalogResult(CatalogModel):
    """User-facing grounded catalog response."""

    answer: NonBlankString
    retrieval_method: RetrievalMethod
    citations: tuple[KnowledgeCitation, ...] = ()


class IndexManifest(CatalogModel):
    """Non-sensitive metadata describing a deterministic local index build."""

    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    embedding_provider: NonBlankString
    embedding_model: NonBlankString | None = None
    embedding_deployment: NonBlankString | None = None
    embedding_dimensions: int = Field(ge=1)
    corpus_hash: NonBlankString
    built_at: NonBlankString

    @model_validator(mode="after")
    def require_consistent_embedding_model(self) -> Self:
        if self.embedding_model is None and self.embedding_deployment is None:
            raise ValueError("embedding model or deployment is required")
        if (
            self.embedding_model is not None
            and self.embedding_deployment is not None
            and self.embedding_model != self.embedding_deployment
        ):
            raise ValueError("embedding model and deployment must match when both are present")
        return self

    @property
    def resolved_embedding_model(self) -> str:
        return self.embedding_model or self.embedding_deployment or ""
