"""Shared safe span-replacement primitive for privacy processing."""

from dataclasses import dataclass

from app.privacy.exceptions import PrivacyProcessingError


@dataclass(frozen=True, slots=True)
class ReplacementSpan:
    """A half-open text span and its safe replacement."""

    start: int
    end: int
    replacement: str


def apply_replacements(text: str, replacements: list[ReplacementSpan]) -> str:
    """Apply validated non-overlapping replacements from right to left."""

    ordered = sorted(replacements, key=lambda item: (item.start, item.end))
    previous_end = 0
    for replacement in ordered:
        if (
            replacement.start < 0
            or replacement.end > len(text)
            or replacement.start >= replacement.end
        ):
            raise PrivacyProcessingError("Privacy processing encountered an invalid protected span")
        if replacement.start < previous_end:
            raise PrivacyProcessingError(
                "Privacy processing encountered overlapping protected spans"
            )
        previous_end = replacement.end

    safe_text = text
    for replacement in reversed(ordered):
        safe_text = (
            safe_text[: replacement.start] + replacement.replacement + safe_text[replacement.end :]
        )
    return safe_text
