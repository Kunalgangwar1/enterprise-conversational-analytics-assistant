"""Safe response restoration for current-request generated tokens."""

import re
from collections.abc import Sequence

from app.privacy.exceptions import PrivacyUnmaskingError
from app.privacy.models import TokenMappingEntry


class ResponseUnmasker:
    """Restore only exact standalone tokens found in an explicit current mapping."""

    def unmask(self, text: str, token_mappings: Sequence[TokenMappingEntry]) -> str:
        if not token_mappings:
            return text

        original_by_token: dict[str, str] = {}
        for entry in token_mappings:
            existing = original_by_token.get(entry.token)
            if existing is not None and existing != entry.original_value:
                raise PrivacyUnmaskingError(
                    "Response unmasking failed because mapping tokens are not unique"
                )
            original_by_token[entry.token] = entry.original_value

        alternatives = "|".join(
            re.escape(token) for token in sorted(original_by_token, key=len, reverse=True)
        )
        token_pattern = re.compile(rf"(?<![A-Za-z0-9_])(?:{alternatives})(?![A-Za-z0-9_])")
        return token_pattern.sub(lambda match: original_by_token[match.group(0)], text)
