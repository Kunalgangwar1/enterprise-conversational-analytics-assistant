"""Request-local reversible token allocation for business identifiers."""

from dataclasses import dataclass

from app.privacy.detectors import EXISTING_TOKEN_PATTERN, IdentifierMatch
from app.privacy.models import TokenMappingEntry
from app.privacy.spans import ReplacementSpan, apply_replacements


@dataclass(frozen=True, slots=True)
class TokenizationResult:
    """Internal identifier-tokenization result."""

    safe_text: str
    token_mappings: tuple[TokenMappingEntry, ...]
    occurrence_count: int


class IdentifierTokenizer:
    """Allocate collision-resistant Txxx tokens within one method call."""

    def tokenize(
        self,
        text: str,
        matches: tuple[IdentifierMatch, ...],
    ) -> TokenizationResult:
        reserved_tokens = set(EXISTING_TOKEN_PATTERN.findall(text))
        token_by_original: dict[str, str] = {}
        entries: list[TokenMappingEntry] = []
        replacements: list[ReplacementSpan] = []
        next_number = 1

        for match in matches:
            original = text[match.start : match.end]
            token = token_by_original.get(original)
            if token is None:
                token, next_number = self._allocate_token(reserved_tokens, next_number)
                reserved_tokens.add(token)
                token_by_original[original] = token
                entries.append(
                    TokenMappingEntry(
                        token=token,
                        original_value=original,
                        identifier_type=match.identifier_type,
                    )
                )
            replacements.append(ReplacementSpan(match.start, match.end, token))

        return TokenizationResult(
            safe_text=apply_replacements(text, replacements),
            token_mappings=tuple(entries),
            occurrence_count=len(matches),
        )

    @staticmethod
    def _allocate_token(reserved_tokens: set[str], next_number: int) -> tuple[str, int]:
        while True:
            token = f"T{next_number:03d}"
            next_number += 1
            if token not in reserved_tokens:
                return token, next_number
