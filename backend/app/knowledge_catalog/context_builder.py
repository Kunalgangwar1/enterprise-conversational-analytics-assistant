"""Deterministic bounded context formatting for catalog evidence."""

from app.knowledge_catalog.models import KnowledgeEvidence


class KnowledgeContextBuilder:
    """Keep evidence provenance separated and within a fixed character budget."""

    def __init__(self, *, max_chars: int) -> None:
        if max_chars < 500:
            raise ValueError("max_chars must be at least 500")
        self._max_chars = max_chars

    def build(self, evidence: tuple[KnowledgeEvidence, ...]) -> str:
        blocks: list[str] = []
        used = 0
        for item in evidence:
            header = (
                f'<evidence id="{item.evidence_id}">\n'
                f"Title: {item.title}\n"
                f"Section: {item.section}\n"
                f"Source: {item.source_path}\n"
                "Content:\n"
            )
            footer = "\n</evidence>"
            remaining = self._max_chars - used
            minimum = len(header) + len(footer) + 1
            if remaining < minimum:
                break
            text = item.text[: remaining - len(header) - len(footer)]
            block = f"{header}{text}{footer}"
            blocks.append(block)
            used += len(block) + (2 if len(blocks) > 1 else 0)
            if len(text) < len(item.text):
                break
        return "\n\n".join(blocks)
