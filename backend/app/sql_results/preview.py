"""Bounded, privacy-protected result previews for LLM summarization."""

import json
import re
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.db.query.models import QueryExecutionResult
from app.privacy.models import TokenMappingEntry
from app.privacy.processor import PrivacyProcessor


class SQLSummaryPreviewBuilder:
    """Serialize a bounded copy of rows, then apply the Phase 9 privacy boundary."""

    def __init__(self, *, max_rows: int, max_chars: int) -> None:
        if max_rows < 1 or max_chars < 1:
            raise ValueError("SQL summary preview limits must be at least 1")
        self._max_rows = max_rows
        self._max_chars = max_chars
        self._privacy_processor = PrivacyProcessor()

    def build(
        self,
        result: QueryExecutionResult,
        token_mappings: Sequence[TokenMappingEntry],
    ) -> str:
        """Return protected preview text without mutating the actual database rows."""

        payload = {
            "columns": result.columns,
            "returned_row_count": result.row_count,
            "truncated": result.truncated,
            "preview_rows": result.rows[: self._max_rows],
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )
        return self.protect_text(serialized, token_mappings)[: self._max_chars]

    def protect_text(
        self,
        text: str,
        token_mappings: Sequence[TokenMappingEntry],
    ) -> str:
        """Reuse current tokens before allocating protection for new identifiers."""

        token_by_original = {entry.original_value: entry.token for entry in token_mappings}
        mapped_text = text
        if token_by_original:
            alternatives = "|".join(
                re.escape(original) for original in sorted(token_by_original, key=len, reverse=True)
            )
            original_pattern = re.compile(rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_])")
            mapped_text = original_pattern.sub(
                lambda match: token_by_original[match.group(0)],
                text,
            )
        return self._privacy_processor.process(mapped_text).safe_text


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
