"""SQLGlot-based restoration of mapped privacy tokens at the database boundary."""

from collections.abc import Mapping, Sequence

import sqlglot
from pydantic import ValidationError
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from app.privacy.detectors import detect_identifiers
from app.privacy.models import TOKEN_VALUE_PATTERN, TokenMappingEntry
from app.sql_results.exceptions import SQLTokenResolutionError


class SQLTokenResolver:
    """Restore only exact known string-literal tokens in PostgreSQL SQL."""

    def resolve(self, sql: str, token_mappings: Sequence[TokenMappingEntry]) -> str:
        original_by_token = _mapping_by_token(token_mappings)
        try:
            statements = sqlglot.parse(sql, read="postgres", error_level=ErrorLevel.RAISE)
        except SqlglotError as exc:
            raise SQLTokenResolutionError(
                "Validated SQL could not be parsed for token resolution"
            ) from exc
        if not statements or any(statement is None for statement in statements):
            raise SQLTokenResolutionError("Validated SQL could not be parsed for token resolution")

        for statement in statements:
            assert statement is not None
            for literal in statement.find_all(exp.Literal):
                if not literal.is_string:
                    continue
                value = literal.this
                original = original_by_token.get(value)
                if original is not None:
                    literal.replace(exp.Literal.string(original))
                elif TOKEN_VALUE_PATTERN.fullmatch(value) is not None:
                    raise SQLTokenResolutionError(
                        "Validated SQL contains a privacy token without a current mapping"
                    )
        return "; ".join(
            statement.sql(dialect="postgres") for statement in statements if statement is not None
        )


def token_mappings_from_session(
    session_mapping: Mapping[str, str] | None,
) -> tuple[TokenMappingEntry, ...]:
    """Adapt the persisted token-to-original shape back to Phase 9 typed entries."""

    if not session_mapping:
        return ()
    if len(set(session_mapping.values())) != len(session_mapping):
        raise SQLTokenResolutionError("Stored privacy token mapping is inconsistent")

    entries: list[TokenMappingEntry] = []
    try:
        for token, original in session_mapping.items():
            matches = detect_identifiers(original)
            exact_matches = [
                match for match in matches if match.start == 0 and match.end == len(original)
            ]
            if len(exact_matches) != 1:
                raise SQLTokenResolutionError("Stored privacy token mapping is invalid")
            entries.append(
                TokenMappingEntry(
                    token=token,
                    original_value=original,
                    identifier_type=exact_matches[0].identifier_type,
                )
            )
    except (TypeError, ValidationError) as exc:
        raise SQLTokenResolutionError("Stored privacy token mapping is invalid") from exc
    return tuple(entries)


def _mapping_by_token(token_mappings: Sequence[TokenMappingEntry]) -> dict[str, str]:
    original_by_token: dict[str, str] = {}
    originals: set[str] = set()
    for entry in token_mappings:
        existing = original_by_token.get(entry.token)
        if existing is not None and existing != entry.original_value:
            raise SQLTokenResolutionError("Privacy token mapping is inconsistent")
        if entry.original_value in originals and existing != entry.original_value:
            raise SQLTokenResolutionError("Privacy token mapping is inconsistent")
        original_by_token[entry.token] = entry.original_value
        originals.add(entry.original_value)
    return original_by_token
