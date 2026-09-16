"""Deterministic standard-library adjacency construction and validation."""

import json
from collections import defaultdict
from pathlib import Path

from pydantic import ValidationError

from app.knowledge_catalog.loader import CatalogHierarchy
from app.knowledge_catalog.models import CatalogChunk
from app.semantica.exceptions import SemanticaGraphError
from app.semantica.models import SemanticaGraph

_RELATED_DOCUMENTS = {
    frozenset(("dataset_claims", "lineage_claims")),
    frozenset(("dataset_encounters", "lineage_encounters")),
}


def build_adjacency(
    chunks: tuple[CatalogChunk, ...], hierarchy: CatalogHierarchy
) -> SemanticaGraph:
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    by_node: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        by_node[chunk.node_id].append(chunk.chunk_id)
    adjacency: dict[str, set[str]] = {chunk_id: set() for chunk_id in chunk_ids}

    for document_chunks in by_node.values():
        for left, right in zip(document_chunks, document_chunks[1:], strict=False):
            _connect(adjacency, left, right)

    for document in hierarchy.documents_by_id.values():
        leaf_children = [child_id for child_id in document.node.children if child_id in by_node]
        for index, left_node in enumerate(leaf_children):
            for right_node in leaf_children[index + 1 :]:
                _connect(adjacency, by_node[left_node][0], by_node[right_node][0])

    for related in _RELATED_DOCUMENTS:
        left_node, right_node = sorted(related)
        if left_node in by_node and right_node in by_node:
            _connect(adjacency, by_node[left_node][0], by_node[right_node][0])

    graph = SemanticaGraph(
        adjacency={
            node_id: tuple(sorted(neighbors)) for node_id, neighbors in sorted(adjacency.items())
        }
    )
    validate_graph(graph, chunk_ids)
    return graph


def validate_graph(graph: SemanticaGraph, chunk_ids: set[str]) -> None:
    if set(graph.adjacency) != chunk_ids:
        raise SemanticaGraphError("Semantica graph nodes do not match indexed chunks")
    for node_id, neighbors in graph.adjacency.items():
        if node_id in neighbors:
            raise SemanticaGraphError(f"Semantica graph contains a self-loop at {node_id}")
        if len(neighbors) != len(set(neighbors)) or not set(neighbors) <= chunk_ids:
            raise SemanticaGraphError(f"Semantica graph contains invalid edges at {node_id}")
        for neighbor in neighbors:
            if node_id not in graph.adjacency[neighbor]:
                raise SemanticaGraphError("Semantica graph edges must be bidirectional")


def write_graph(path: Path, graph: SemanticaGraph) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(graph.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_graph(path: Path, *, chunk_ids: set[str] | None = None) -> SemanticaGraph:
    try:
        graph = SemanticaGraph.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        raise SemanticaGraphError("Semantica adjacency artifact is missing or invalid") from exc
    if chunk_ids is not None:
        validate_graph(graph, chunk_ids)
    return graph


def _connect(adjacency: dict[str, set[str]], left: str, right: str) -> None:
    if left == right:
        return
    adjacency[left].add(right)
    adjacency[right].add(left)
