"""Conservative irreversible redaction for generic PII."""

from dataclasses import dataclass

from app.privacy.detectors import EMAIL_PATTERN, PHONE_PATTERN
from app.privacy.spans import ReplacementSpan, apply_replacements


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Internal generic-PII redaction result and safe counts."""

    safe_text: str
    email_count: int
    phone_count: int


class PIIRedactor:
    """Redact supported generic PII categories without retaining their values."""

    def redact(self, text: str) -> RedactionResult:
        email_matches = tuple(EMAIL_PATTERN.finditer(text))
        email_safe_text = apply_replacements(
            text,
            [ReplacementSpan(match.start(), match.end(), "[EMAIL]") for match in email_matches],
        )

        phone_matches = tuple(PHONE_PATTERN.finditer(email_safe_text))
        safe_text = apply_replacements(
            email_safe_text,
            [ReplacementSpan(match.start(), match.end(), "[PHONE]") for match in phone_matches],
        )
        return RedactionResult(
            safe_text=safe_text,
            email_count=len(email_matches),
            phone_count=len(phone_matches),
        )
