"""Deterministic heading-aware catalog chunking tests."""

from app.knowledge_catalog.chunker import CatalogChunker
from app.knowledge_catalog.loader import CatalogHierarchy
from app.knowledge_catalog.models import CatalogDocument, CatalogNode


def test_real_corpus_chunk_ids_and_rebuild_are_deterministic(hierarchy: CatalogHierarchy) -> None:
    chunker = CatalogChunker(chunk_size_chars=300, overlap_chars=40)

    first = chunker.chunk_hierarchy(hierarchy)
    second = chunker.chunk_hierarchy(hierarchy)

    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert len({item.chunk_id for item in first}) == len(first)


def test_headings_and_metadata_are_preserved(hierarchy: CatalogHierarchy) -> None:
    chunks = CatalogChunker(chunk_size_chars=1_200, overlap_chars=150).chunk_hierarchy(hierarchy)
    claim_chunks = [chunk for chunk in chunks if chunk.node_id == "dataset_claims"]

    assert {chunk.section for chunk in claim_chunks} >= {
        "Grain and relationships",
        "Financial measures",
    }
    assert all(chunk.source_path == "datasets/claims.md" for chunk in claim_chunks)
    assert all(chunk.domain == "claims" for chunk in claim_chunks)
    assert any("## Financial measures" in chunk.text for chunk in claim_chunks)


def test_long_section_is_bounded_and_overlap_is_deterministic() -> None:
    text = "# Long section\n\n" + " ".join(f"term{index}" for index in range(250))
    document = CatalogDocument(
        node=CatalogNode(
            id="long_leaf",
            title="Long Leaf",
            node_type="dataset",
            summary="Long test leaf.",
            parent="root",
            source_path="datasets/long.md",
        ),
        text=text,
    )
    chunker = CatalogChunker(chunk_size_chars=240, overlap_chars=40)

    first = chunker.chunk_document(document)
    second = chunker.chunk_document(document)

    assert len(first) > 2
    assert all(len(chunk.text) <= 240 for chunk in first)
    assert [chunk.text for chunk in first] == [chunk.text for chunk in second]
    assert first[0].text[-20:] in first[1].text
