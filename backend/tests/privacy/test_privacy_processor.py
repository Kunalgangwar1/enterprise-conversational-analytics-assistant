"""Unit tests for deterministic identifier tokenization and PII redaction."""

import logging

import pytest

from app.privacy import IdentifierType, PrivacyProcessor


@pytest.fixture
def processor() -> PrivacyProcessor:
    return PrivacyProcessor()


@pytest.mark.parametrize(
    ("identifier", "identifier_type"),
    [
        ("M000245", IdentifierType.MEMBER),
        ("P00125", IdentifierType.PROVIDER),
        ("F0042", IdentifierType.FACILITY),
        ("E0000125", IdentifierType.ENCOUNTER),
        ("C0000789", IdentifierType.CLAIM),
        ("A0000042", IdentifierType.APPOINTMENT),
    ],
)
def test_each_seeded_identifier_type_is_tokenized(
    processor: PrivacyProcessor,
    identifier: str,
    identifier_type: IdentifierType,
) -> None:
    result = processor.process(f"Find {identifier}.")

    assert result.safe_text == "Find T001."
    assert len(result.token_mappings) == 1
    assert result.token_mappings[0].original_value == identifier
    assert result.token_mappings[0].identifier_type is identifier_type
    assert result.redaction_counts.identifier_occurrences == 1


@pytest.mark.parametrize(
    "text",
    [
        "Show the top 5 providers",
        "claims in 2026",
        "paid amount over 1000",
        "M00245 has the wrong width",
        "P000001 has the wrong width",
        "prefixM000245suffix is embedded",
        "m000245 is not a seeded identifier",
    ],
)
def test_unrelated_values_are_not_tokenized(processor: PrivacyProcessor, text: str) -> None:
    result = processor.process(text)

    assert result.safe_text == text
    assert result.token_mappings == ()


def test_distinct_and_repeated_identifiers_use_first_occurrence_order(
    processor: PrivacyProcessor,
) -> None:
    text = "Compare M000245 with C0000012, then M000245 again."

    result = processor.process(text)

    assert result.safe_text == "Compare T001 with T002, then T001 again."
    assert [(entry.token, entry.original_value) for entry in result.token_mappings] == [
        ("T001", "M000245"),
        ("T002", "C0000012"),
    ]
    assert result.redaction_counts.identifier_occurrences == 3


def test_token_allocation_is_deterministic_and_request_scoped(
    processor: PrivacyProcessor,
) -> None:
    text = "Compare M000245 with P00125."

    first = processor.process(text)
    second = processor.process(text)

    assert first == second
    assert [entry.token for entry in second.token_mappings] == ["T001", "T002"]


def test_existing_standalone_tokens_are_not_reallocated(processor: PrivacyProcessor) -> None:
    result = processor.process("Keep T001 and find M000245 plus C0000012.")

    assert result.safe_text == "Keep T001 and find T002 plus T003."
    assert [entry.token for entry in result.token_mappings] == ["T002", "T003"]


def test_token_text_embedded_in_a_word_does_not_reserve_a_token(
    processor: PrivacyProcessor,
) -> None:
    result = processor.process("Keep prefixT001suffix and find M000245.")

    assert result.safe_text == "Keep prefixT001suffix and find T001."


def test_email_is_irreversibly_redacted(processor: PrivacyProcessor) -> None:
    result = processor.process("Send results to alice@example.com and bob.smith@example.org.")

    assert result.safe_text == "Send results to [EMAIL] and [EMAIL]."
    assert result.redaction_counts.email_occurrences == 2
    assert result.token_mappings == ()


@pytest.mark.parametrize(
    "phone",
    [
        "(415) 555-0137",
        "415-555-0137",
        "+1 415 555 0137",
    ],
)
def test_supported_us_phone_formats_are_redacted(
    processor: PrivacyProcessor,
    phone: str,
) -> None:
    result = processor.process(f"Call {phone} for details.")

    assert result.safe_text == "Call [PHONE] for details."
    assert result.redaction_counts.phone_occurrences == 1


@pytest.mark.parametrize("number", ["2500", "2026", "1000", "42"])
def test_analytics_numbers_are_not_phone_numbers(
    processor: PrivacyProcessor,
    number: str,
) -> None:
    text = f"Show paid amount over {number}."

    assert processor.process(text).safe_text == text


def test_dates_are_preserved(processor: PrivacyProcessor) -> None:
    text = "Show claims from January 2026 and 2026-01-15."

    assert processor.process(text).safe_text == text


def test_multiple_identifiers_and_pii_are_processed_without_offset_corruption(
    processor: PrivacyProcessor,
) -> None:
    text = (
        "Member M000245 used provider P00125 for claim C0000789. "
        "Email alice@example.com or call (415) 555-0137."
    )

    result = processor.process(text)

    assert result.safe_text == (
        "Member T001 used provider T002 for claim T003. Email [EMAIL] or call [PHONE]."
    )
    assert result.redaction_counts.identifier_occurrences == 3
    assert result.redaction_counts.email_occurrences == 1
    assert result.redaction_counts.phone_occurrences == 1


def test_email_priority_resolves_a_realistic_phone_overlap(
    processor: PrivacyProcessor,
) -> None:
    result = processor.process("Contact 415-555-0137@example.com.")

    assert result.safe_text == "Contact [EMAIL]."
    assert result.redaction_counts.email_occurrences == 1
    assert result.redaction_counts.phone_occurrences == 0


def test_privacy_processing_does_not_log_sensitive_values(
    processor: PrivacyProcessor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    protected_values = ("M000245", "alice@example.com", "(415) 555-0137")

    with caplog.at_level(logging.DEBUG):
        processor.process("Member M000245 can be reached at alice@example.com or (415) 555-0137.")

    log_output = caplog.text
    assert all(value not in log_output for value in protected_values)


def test_processor_requires_no_database_or_azure_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in (
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
    ):
        monkeypatch.delenv(variable, raising=False)

    result = PrivacyProcessor().process("Find member M000245.")

    assert result.safe_text == "Find member T001."
    assert result.as_session_mapping() == {"T001": "M000245"}
