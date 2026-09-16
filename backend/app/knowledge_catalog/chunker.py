"""Heading-aware deterministic chunking for leaf catalog documents."""

import hashlib
import re
from collections.abc import Iterable

from app.knowledge_catalog.loader import CatalogHierarchy
from app.knowledge_catalog.models import CatalogChunk, CatalogDocument

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class CatalogChunker:
    """Split Markdown by heading and bounded paragraph windows."""

    def __init__(
        self,
        *,
        chunk_size_chars: int,
        overlap_chars: int,
        minimum_chunk_size_chars: int = 100,
    ) -> None:
        if minimum_chunk_size_chars < 1:
            raise ValueError("minimum_chunk_size_chars must be positive")
        if chunk_size_chars < minimum_chunk_size_chars:
            raise ValueError(f"chunk_size_chars must be at least {minimum_chunk_size_chars}")
        if overlap_chars < 0 or overlap_chars >= chunk_size_chars:
            raise ValueError("overlap_chars must be non-negative and smaller than chunk size")
        self._chunk_size = chunk_size_chars
        self._overlap = overlap_chars

    def chunk_hierarchy(self, hierarchy: CatalogHierarchy) -> tuple[CatalogChunk, ...]:
        chunks: list[CatalogChunk] = []
        for document in sorted(hierarchy.leaf_documents, key=lambda item: item.node.source_path):
            chunks.extend(self.chunk_document(document))
        return tuple(chunks)

    def chunk_document(self, document: CatalogDocument) -> tuple[CatalogChunk, ...]:
        chunks: list[CatalogChunk] = []
        for section_index, (section, section_text) in enumerate(_markdown_sections(document.text)):
            for chunk_index, text in enumerate(self._split_section(section_text)):
                identity = (
                    f"{document.node.source_path}:{document.node.id}:{section_index}:{chunk_index}"
                )
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
                chunks.append(
                    CatalogChunk(
                        chunk_id=f"chunk_{digest}",
                        node_id=document.node.id,
                        title=document.node.title,
                        section=section,
                        source_path=document.node.source_path,
                        node_type=document.node.node_type,
                        domain=document.node.domain,
                        text=text,
                    )
                )
        return tuple(chunks)

    def _split_section(self, text: str) -> tuple[str, ...]:
        if len(text) <= self._chunk_size:
            return (text.strip(),)
        chunks: list[str] = []
        start = 0
        while start < len(text):
            hard_end = min(start + self._chunk_size, len(text))
            end = hard_end
            if hard_end < len(text):
                boundary = max(
                    text.rfind("\n\n", start, hard_end), text.rfind("\n", start, hard_end)
                )
                if boundary > start + self._chunk_size // 2:
                    end = boundary
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(end - self._overlap, start + 1)
        return tuple(chunks)


def _markdown_sections(text: str) -> Iterable[tuple[str, str]]:
    current_heading = "Overview"
    current_lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else _HEADING_PATTERN.match(line)
        if match:
            if any(part.strip() for part in current_lines):
                yield current_heading, "\n".join(current_lines).strip()
            current_heading = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if any(part.strip() for part in current_lines):
        yield current_heading, "\n".join(current_lines).strip()
