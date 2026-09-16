"""Deterministic field-aware search over registered synthetic datasets."""

import re

from app.data_discovery.models import DataDiscoveryResult, DatasetMatch, DatasetRegistration

_TOKEN = re.compile(r"[a-z0-9]+")
_BROAD_TERMS = {"lineage", "policy", "governance", "retention", "meaning"}
_STOP_WORDS = {
    "a",
    "about",
    "and",
    "contains",
    "data",
    "dataset",
    "find",
    "for",
    "is",
    "me",
    "of",
    "the",
    "which",
    "where",
}


class DataDiscoveryService:
    """Rank dataset metadata without LLM, embeddings, or database access."""

    def __init__(self, registrations: tuple[DatasetRegistration, ...], *, top_k: int) -> None:
        self._registrations = registrations
        self._top_k = top_k

    def search(self, safe_question: str) -> DataDiscoveryResult:
        normalized = _normalize(safe_question)
        query_tokens = set(_tokens(normalized)) - _STOP_WORDS
        if not query_tokens or query_tokens & _BROAD_TERMS:
            return DataDiscoveryResult()
        matches = [
            match
            for item in self._registrations
            if (match := _score(item, normalized, query_tokens))
        ]
        matches.sort(key=lambda item: (-item.score, item.dataset))
        return DataDiscoveryResult(matches=tuple(matches[: self._top_k]))


def _score(
    item: DatasetRegistration,
    query: str,
    query_tokens: set[str],
) -> DatasetMatch | None:
    score = 0.0
    matched: list[str] = []
    table_phrase = _normalize(item.table)
    if query == table_phrase or query == _normalize(item.dataset):
        score = 1.0
        matched.append("table")
    elif set(_tokens(table_phrase)) <= query_tokens:
        score = max(score, 0.72)
        matched.append("table")

    for alias in item.table_aliases:
        if _contains_phrase(query, alias):
            score = max(score, 0.68)
            matched.append(f"alias:{alias}")
    for column, aliases in item.columns.items():
        if _contains_phrase(query, column):
            score = max(score, 0.92)
            matched.append(f"column:{column}")
        for alias in aliases:
            if _contains_phrase(query, alias):
                score = max(score, 0.88)
                matched.append(f"column_alias:{alias}")

    searchable = " ".join(
        [item.dataset, item.repository, item.domain, item.description, *item.table_aliases]
    )
    overlap = query_tokens & (set(_tokens(searchable)) - _STOP_WORDS)
    if overlap:
        score = min(1.0, max(score, 0.22 + 0.09 * len(overlap)))
        matched.extend(f"keyword:{token}" for token in sorted(overlap))
    if score < 0.30:
        return None
    return DatasetMatch(
        dataset=item.dataset,
        repository=item.repository,
        table=item.table,
        domain=item.domain,
        description=item.description,
        matched_fields=tuple(dict.fromkeys(matched)),
        score=round(score, 4),
    )


def _contains_phrase(query: str, value: str) -> bool:
    phrase = _normalize(value)
    return bool(phrase) and f" {phrase} " in f" {query} "


def _normalize(value: str) -> str:
    return " ".join(_tokens(value))


def _tokens(value: str) -> list[str]:
    return _TOKEN.findall(value.lower().replace("_", " ").replace("-", " "))
