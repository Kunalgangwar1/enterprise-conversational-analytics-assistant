"""Unit tests for exact current-request response unmasking."""

import pytest

from app.privacy import (
    IdentifierType,
    PrivacyUnmaskingError,
    ResponseUnmasker,
    TokenMappingEntry,
)


def _entry(token: str, original: str) -> TokenMappingEntry:
    return TokenMappingEntry(
        token=token,
        original_value=original,
        identifier_type=IdentifierType.MEMBER,
    )


def test_known_tokens_are_restored_and_unknown_tokens_remain() -> None:
    text = "Member T001 has 4 claims; T999 is unrelated."

    result = ResponseUnmasker().unmask(text, [_entry("T001", "M000245")])

    assert result == "Member M000245 has 4 claims; T999 is unrelated."


def test_token_substrings_and_redaction_placeholders_are_not_restored() -> None:
    text = "prefixT001suffix T001 [EMAIL] [PHONE]"

    result = ResponseUnmasker().unmask(text, [_entry("T001", "M000245")])

    assert result == "prefixT001suffix M000245 [EMAIL] [PHONE]"


def test_empty_mapping_does_not_guess_tokens() -> None:
    assert ResponseUnmasker().unmask("Unknown T001 remains.", []) == "Unknown T001 remains."


def test_inconsistent_mapping_error_does_not_expose_original_values() -> None:
    mappings = [_entry("T001", "M000245"), _entry("T001", "M000999")]

    with pytest.raises(PrivacyUnmaskingError) as captured:
        ResponseUnmasker().unmask("Member T001", mappings)

    message = str(captured.value)
    assert "M000245" not in message
    assert "M000999" not in message
