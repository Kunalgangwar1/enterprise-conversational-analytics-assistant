"""Lightweight deterministic retrieval over Data Quality guidance."""

import re

from app.data_quality.models import DataQualityDocument, DataQualityEvidence

_TOKEN = re.compile(r"[a-z0-9_]+")
_STOP = {"a", "and", "apply", "for", "is", "of", "the", "to", "what", "which"}


class DataQualityRetriever:
    def __init__(self, documents: tuple[DataQualityDocument, ...], *, top_k: int) -> None:
        self._documents = documents
        self._top_k = top_k

    def retrieve(self, safe_question: str) -> tuple[DataQualityEvidence, ...]:
        query = set(_tokens(safe_question)) - _STOP
        if not query:
            return ()
        ranked: list[tuple[float, DataQualityDocument]] = []
        for document in self._documents:
            metadata = " ".join(
                filter(
                    None,
                    [document.title, document.topic, document.dimension, document.dataset],
                )
            )
            metadata_tokens = set(_tokens(metadata))
            text_tokens = set(_tokens(document.text))
            metadata_overlap = query & metadata_tokens
            text_overlap = query & text_tokens
            if not metadata_overlap and not text_overlap:
                continue
            score = min(1.0, 0.16 * len(metadata_overlap) + 0.05 * len(text_overlap))
            if document.dimension and document.dimension.lower() in query:
                score = max(score, 0.90)
            if document.dataset and document.dataset.lower() in query:
                score = max(score, 0.82)
            if score >= 0.20:
                ranked.append((score, document))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return tuple(
            DataQualityEvidence(
                evidence_id=document.id,
                title=document.title,
                topic=document.topic,
                dimension=document.dimension,
                dataset=document.dataset,
                source_path=document.source_path,
                text=document.text,
                rank=rank,
                score=round(score, 4),
            )
            for rank, (score, document) in enumerate(ranked[: self._top_k], start=1)
        )


def _tokens(value: str) -> list[str]:
    return _TOKEN.findall(value.lower().replace("-", "_"))
