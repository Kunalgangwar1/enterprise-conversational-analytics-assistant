"""Dedicated Semantica chunk and adjacency tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.knowledge_catalog.loader import CatalogHierarchy
from app.semantica.chunker import SemanticaChunker
from app.semantica.graph import build_adjacency, validate_graph


def test_semantica_defaults_are_900_and_120() -> None:
    settings = Settings(_env_file=None)

    assert settings.semantica_chunk_size_chars == 900
    assert settings.semantica_chunk_overlap_chars == 120


def test_semantica_settings_reject_invalid_overlap_and_hops() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, semantica_chunk_size_chars=100, semantica_chunk_overlap_chars=100)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, semantica_max_hops=3)


def test_semantica_chunker_accepts_contract_minimum_size(
    hierarchy: CatalogHierarchy,
) -> None:
    chunks = SemanticaChunker(chunk_size_chars=1, overlap_chars=0).chunk_hierarchy(hierarchy)

    assert chunks
    assert all(len(chunk.text) <= 1 for chunk in chunks)


def test_chunk_ids_and_metadata_are_stable(hierarchy: CatalogHierarchy) -> None:
    chunker = SemanticaChunker(chunk_size_chars=900, overlap_chars=120)

    first = chunker.chunk_hierarchy(hierarchy)
    second = chunker.chunk_hierarchy(hierarchy)

    assert first == second
    assert all(chunk.chunk_id.startswith("sem_") for chunk in first)
    claim = next(chunk for chunk in first if chunk.node_id == "dataset_claims")
    assert claim.source_path == "datasets/claims.md"
    assert claim.domain == "claims"
    assert claim.section


def test_graph_is_valid_deterministic_and_connects_sequential_chunks(
    hierarchy: CatalogHierarchy,
) -> None:
    chunks = SemanticaChunker(chunk_size_chars=900, overlap_chars=120).chunk_hierarchy(hierarchy)
    first = build_adjacency(chunks, hierarchy)
    second = build_adjacency(chunks, hierarchy)

    assert first == second
    assert set(first.adjacency) == {chunk.chunk_id for chunk in chunks}
    validate_graph(first, set(first.adjacency))
    assert all(node not in neighbors for node, neighbors in first.adjacency.items())
    assert all(len(neighbors) == len(set(neighbors)) for neighbors in first.adjacency.values())

    claim_chunks = [chunk.chunk_id for chunk in chunks if chunk.node_id == "dataset_claims"]
    assert claim_chunks[1] in first.adjacency[claim_chunks[0]]
