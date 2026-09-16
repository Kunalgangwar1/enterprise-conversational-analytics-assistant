"""Safe loading and validation of the explicit Markdown catalog hierarchy."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.knowledge_catalog.exceptions import CatalogHierarchyError, CatalogLoadError
from app.knowledge_catalog.models import CatalogDocument, CatalogNode, CatalogNodeType


@dataclass(frozen=True, slots=True)
class CatalogHierarchy:
    """Validated catalog graph rooted at exactly one explicit root node."""

    root: CatalogNode
    documents_by_id: dict[str, CatalogDocument]

    def document(self, node_id: str) -> CatalogDocument:
        try:
            return self.documents_by_id[node_id]
        except KeyError as exc:
            raise CatalogHierarchyError(f"Unknown catalog node: {node_id}") from exc

    def children(self, node_id: str) -> tuple[CatalogDocument, ...]:
        document = self.document(node_id)
        return tuple(self.document(child_id) for child_id in document.node.children)

    @property
    def leaf_documents(self) -> tuple[CatalogDocument, ...]:
        return tuple(
            document for document in self.documents_by_id.values() if not document.node.children
        )


class CatalogLoader:
    """Load YAML-front-matter Markdown without leaving the configured root."""

    def __init__(self, catalog_root: Path) -> None:
        self._catalog_root = catalog_root.resolve()

    def load(self) -> CatalogHierarchy:
        if not self._catalog_root.is_dir():
            raise CatalogLoadError(f"Knowledge Catalog directory not found: {self._catalog_root}")

        documents: dict[str, CatalogDocument] = {}
        for source_path in sorted(self._catalog_root.rglob("*.md")):
            document = self._load_document(source_path)
            if document.node.id in documents:
                raise CatalogHierarchyError(f"Duplicate catalog node ID: {document.node.id}")
            documents[document.node.id] = document

        if not documents:
            raise CatalogLoadError("Knowledge Catalog contains no Markdown documents")
        return _validate_hierarchy(documents)

    def _load_document(self, source_path: Path) -> CatalogDocument:
        resolved_path = source_path.resolve()
        if not resolved_path.is_relative_to(self._catalog_root):
            raise CatalogLoadError(f"Catalog source path escapes configured root: {source_path}")
        try:
            raw_text = resolved_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CatalogLoadError(f"Unable to read catalog document: {source_path}") from exc

        metadata, body = _split_front_matter(raw_text, source_path)
        try:
            node = CatalogNode.model_validate(
                {
                    **metadata,
                    "source_path": resolved_path.relative_to(self._catalog_root).as_posix(),
                }
            )
            return CatalogDocument(node=node, text=body.strip())
        except ValidationError as exc:
            raise CatalogLoadError(f"Invalid catalog metadata in {source_path}: {exc}") from exc


def _split_front_matter(raw_text: str, source_path: Path) -> tuple[dict[str, object], str]:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise CatalogLoadError(f"Catalog document lacks YAML front matter: {source_path}")
    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line == "---"
        )
    except StopIteration as exc:
        raise CatalogLoadError(f"Catalog front matter is not closed: {source_path}") from exc
    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing_index]))
    except yaml.YAMLError as exc:
        raise CatalogLoadError(f"Malformed catalog front matter: {source_path}") from exc
    if not isinstance(metadata, dict):
        raise CatalogLoadError(f"Catalog front matter must be a mapping: {source_path}")
    body = "\n".join(lines[closing_index + 1 :]).strip()
    if not body:
        raise CatalogLoadError(f"Catalog document body must not be empty: {source_path}")
    return metadata, body


def _validate_hierarchy(documents: dict[str, CatalogDocument]) -> CatalogHierarchy:
    roots = [
        item.node for item in documents.values() if item.node.node_type == CatalogNodeType.ROOT
    ]
    if len(roots) != 1:
        raise CatalogHierarchyError("Knowledge Catalog must contain exactly one root node")
    root = roots[0]
    if root.parent is not None:
        raise CatalogHierarchyError("Catalog root must not declare a parent")

    for document in documents.values():
        node = document.node
        if len(node.children) != len(set(node.children)):
            raise CatalogHierarchyError(f"Catalog node {node.id} contains duplicate child IDs")
        for child_id in node.children:
            if child_id not in documents:
                raise CatalogHierarchyError(
                    f"Catalog node {node.id} references missing child {child_id}"
                )

    _reject_cycles_and_unreachable_nodes(root.id, documents)

    for document in documents.values():
        node = document.node
        for child_id in node.children:
            child = documents[child_id]
            if child.node.parent != node.id:
                raise CatalogHierarchyError(
                    f"Parent/child mismatch: {node.id} -> {child_id}, parent={child.node.parent!r}"
                )
        if node.id != root.id:
            if node.parent is None or node.parent not in documents:
                raise CatalogHierarchyError(
                    f"Parent/child mismatch: catalog node {node.id} has no valid parent"
                )
            if node.id not in documents[node.parent].node.children:
                raise CatalogHierarchyError(
                    f"Parent/child mismatch: {node.id} is absent from {node.parent} children"
                )

    return CatalogHierarchy(root=root, documents_by_id=documents)


def _reject_cycles_and_unreachable_nodes(
    root_id: str, documents: dict[str, CatalogDocument]
) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise CatalogHierarchyError(f"Catalog hierarchy contains a cycle at {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child_id in documents[node_id].node.children:
            visit(child_id)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(root_id)
    unreachable = sorted(set(documents) - visited)
    if unreachable:
        raise CatalogHierarchyError(
            f"Catalog nodes are unreachable from root: {', '.join(unreachable)}"
        )
