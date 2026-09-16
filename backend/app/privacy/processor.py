"""Main deterministic privacy preprocessing boundary."""

from app.privacy.detectors import detect_identifiers
from app.privacy.models import PrivacyResult, RedactionCounts
from app.privacy.redactor import PIIRedactor
from app.privacy.tokenizer import IdentifierTokenizer


class PrivacyProcessor:
    """Tokenize seeded identifiers and redact supported generic PII per request."""

    def __init__(
        self,
        *,
        tokenizer: IdentifierTokenizer | None = None,
        redactor: PIIRedactor | None = None,
    ) -> None:
        self._tokenizer = tokenizer or IdentifierTokenizer()
        self._redactor = redactor or PIIRedactor()

    def process(self, text: str) -> PrivacyResult:
        """Return LLM-safe text and the current request's reversible mappings."""

        tokenized = self._tokenizer.tokenize(text, detect_identifiers(text))
        redacted = self._redactor.redact(tokenized.safe_text)
        return PrivacyResult(
            safe_text=redacted.safe_text,
            token_mappings=tokenized.token_mappings,
            redaction_counts=RedactionCounts(
                identifier_occurrences=tokenized.occurrence_count,
                email_occurrences=redacted.email_count,
                phone_occurrences=redacted.phone_count,
            ),
        )
