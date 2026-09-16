"""Bounded provenance-preserving Data Quality evidence context."""

from app.data_quality.models import DataQualityEvidence


class DataQualityContextBuilder:
    def __init__(self, *, max_chars: int) -> None:
        if max_chars < 500:
            raise ValueError("max_chars must be at least 500")
        self._max_chars = max_chars

    def build(self, evidence: tuple[DataQualityEvidence, ...]) -> str:
        blocks: list[str] = []
        used = 0
        for item in evidence:
            header = (
                f'<evidence id="{item.evidence_id}">\n'
                f"Title: {item.title}\nTopic: {item.topic}\nSource: {item.source_path}\n"
                "Content:\n"
            )
            footer = "\n</evidence>"
            separator = 2 if blocks else 0
            remaining = self._max_chars - used - separator
            if remaining <= len(header) + len(footer):
                break
            text = item.text[: remaining - len(header) - len(footer)]
            block = f"{header}{text}{footer}"
            blocks.append(block)
            used += separator + len(block)
            if len(text) < len(item.text):
                break
        return "\n\n".join(blocks)
