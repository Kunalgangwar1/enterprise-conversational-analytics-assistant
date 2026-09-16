"""AST-only SQL privacy-token restoration tests."""

import pytest
import sqlglot

from app.privacy import IdentifierType, TokenMappingEntry
from app.sql_results import SQLTokenResolutionError, SQLTokenResolver
from app.sql_results.token_resolver import token_mappings_from_session


def _mapping(token: str, original: str, kind: IdentifierType) -> TokenMappingEntry:
    return TokenMappingEntry(token=token, original_value=original, identifier_type=kind)


def test_exact_string_literal_is_resolved_to_current_original() -> None:
    sql = "SELECT * FROM members WHERE member_external_id = 'T001'"

    resolved = SQLTokenResolver().resolve(
        sql,
        (_mapping("T001", "M000245", IdentifierType.MEMBER),),
    )

    assert "member_external_id = 'M000245'" in resolved
    assert "T001" not in resolved


def test_two_known_literal_tokens_are_resolved() -> None:
    sql = (
        "SELECT * FROM encounters WHERE member_external_id = 'T001' "
        "AND provider_external_id = 'T002'"
    )
    mappings = (
        _mapping("T001", "M000245", IdentifierType.MEMBER),
        _mapping("T002", "P00042", IdentifierType.PROVIDER),
    )

    resolved = SQLTokenResolver().resolve(sql, mappings)

    assert "'M000245'" in resolved
    assert "'P00042'" in resolved


def test_unknown_token_literal_fails_closed() -> None:
    with pytest.raises(SQLTokenResolutionError, match="without a current mapping"):
        SQLTokenResolver().resolve("SELECT * FROM members WHERE id = 'T999'", ())


def test_alias_comment_and_larger_string_are_not_modified() -> None:
    sql = "SELECT total AS T001 FROM claims /* T001 */ WHERE note = 'prefix T001 suffix'"
    mapping = (_mapping("T001", "M000245", IdentifierType.MEMBER),)

    resolved = SQLTokenResolver().resolve(sql, mapping)

    assert "AS T001" in resolved
    assert "T001" in resolved
    assert "'prefix T001 suffix'" in resolved
    assert "M000245" not in resolved


def test_sql_without_token_literals_is_semantically_unchanged() -> None:
    sql = "SELECT claim_status, COUNT(*) AS claim_count FROM claims GROUP BY claim_status"

    resolved = SQLTokenResolver().resolve(sql, ())

    assert sqlglot.parse_one(resolved, read="postgres") == sqlglot.parse_one(sql, read="postgres")


def test_serialized_session_mapping_adapts_to_phase_nine_entries() -> None:
    entries = token_mappings_from_session({"T001": "M000245", "T002": "P00042"})

    assert entries == (
        _mapping("T001", "M000245", IdentifierType.MEMBER),
        _mapping("T002", "P00042", IdentifierType.PROVIDER),
    )


def test_invalid_serialized_session_mapping_fails_closed() -> None:
    with pytest.raises(SQLTokenResolutionError, match="invalid"):
        token_mappings_from_session({"T001": "not-a-supported-identifier"})
