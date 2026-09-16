"""Catalog front matter and hierarchy validation tests."""

from pathlib import Path

import pytest

from app.knowledge_catalog.exceptions import CatalogHierarchyError, CatalogLoadError
from app.knowledge_catalog.loader import CatalogLoader


def test_synthetic_hierarchy_loads_with_one_root_and_unique_nodes(catalog_root: Path) -> None:
    hierarchy = CatalogLoader(catalog_root).load()

    assert hierarchy.root.id == "catalog_root"
    assert len(hierarchy.documents_by_id) == len(set(hierarchy.documents_by_id))
    assert {"dataset_claims", "dataset_appointments", "policy_data_access"}.issubset(
        hierarchy.documents_by_id
    )


def test_invalid_child_reference_fails(tmp_path: Path) -> None:
    _write_doc(tmp_path / "root.md", "root", "root", children=["missing"])

    with pytest.raises(CatalogHierarchyError, match="missing child"):
        CatalogLoader(tmp_path).load()


def test_cycle_fails(tmp_path: Path) -> None:
    _write_doc(tmp_path / "root.md", "root", "root", children=["a"])
    _write_doc(tmp_path / "a.md", "a", "domain", parent="root", children=["b"])
    _write_doc(tmp_path / "b.md", "b", "dataset", parent="a", children=["a"])

    with pytest.raises(CatalogHierarchyError, match="cycle"):
        CatalogLoader(tmp_path).load()


def test_parent_child_inconsistency_fails(tmp_path: Path) -> None:
    _write_doc(tmp_path / "root.md", "root", "root", children=["leaf"])
    _write_doc(tmp_path / "leaf.md", "leaf", "dataset", parent="wrong")

    with pytest.raises(CatalogHierarchyError, match="Parent/child mismatch"):
        CatalogLoader(tmp_path).load()


def test_symlink_source_outside_catalog_is_rejected(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    outside = tmp_path / "outside.md"
    _write_doc(outside, "root", "root")
    (catalog / "catalog_root.md").symlink_to(outside)

    with pytest.raises(CatalogLoadError, match="escapes"):
        CatalogLoader(catalog).load()


def test_catalog_uses_only_generic_synthetic_content(catalog_root: Path) -> None:
    content = "\n".join(path.read_text(encoding="utf-8") for path in catalog_root.rglob("*.md"))

    assert "synthetic" in content.lower()
    assert "cognizant" not in content.lower()
    assert "optum" not in content.lower()


def _write_doc(
    path: Path,
    node_id: str,
    node_type: str,
    *,
    parent: str | None = None,
    children: list[str] | None = None,
) -> None:
    lines = [
        "---",
        f"id: {node_id}",
        f"title: {node_id.title()}",
        f"node_type: {node_type}",
        f"summary: Summary for {node_id}.",
    ]
    if parent:
        lines.append(f"parent: {parent}")
    if children:
        lines.append("children:")
        lines.extend(f"  - {child}" for child in children)
    lines.extend(["---", f"# {node_id.title()}", "Synthetic content."])
    path.write_text("\n".join(lines), encoding="utf-8")
