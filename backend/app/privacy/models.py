"""Typed provider-neutral models for privacy preprocessing."""

import re
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TOKEN_VALUE_PATTERN = re.compile(r"T\d{3,}\Z")


class PrivacyModel(BaseModel):
    """Strict immutable base model for privacy values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class IdentifierType(StrEnum):
    """Synthetic business identifier categories supported by the seed data."""

    MEMBER = "member"
    PROVIDER = "provider"
    FACILITY = "facility"
    ENCOUNTER = "encounter"
    CLAIM = "claim"
    APPOINTMENT = "appointment"


class RedactionCategory(StrEnum):
    """Irreversible generic PII categories supported by this baseline."""

    EMAIL = "email"
    PHONE = "phone"


class TokenMappingEntry(PrivacyModel):
    """One sensitive, request-local reversible identifier mapping."""

    token: NonBlankString
    original_value: NonBlankString
    identifier_type: IdentifierType

    @field_validator("token")
    @classmethod
    def require_generated_token_format(cls, value: str) -> str:
        if TOKEN_VALUE_PATTERN.fullmatch(value) is None:
            raise ValueError("token must use the Txxx generated-token format")
        return value


class RedactionCounts(PrivacyModel):
    """Non-sensitive occurrence counts produced during preprocessing."""

    identifier_occurrences: int = Field(default=0, ge=0)
    email_occurrences: int = Field(default=0, ge=0)
    phone_occurrences: int = Field(default=0, ge=0)


class PrivacyResult(PrivacyModel):
    """Safe request text plus the minimum mapping needed for response reversal."""

    safe_text: str
    token_mappings: tuple[TokenMappingEntry, ...] = ()
    redaction_counts: RedactionCounts = Field(default_factory=RedactionCounts)

    @model_validator(mode="after")
    def require_one_to_one_mappings(self) -> Self:
        tokens = [entry.token for entry in self.token_mappings]
        originals = [entry.original_value for entry in self.token_mappings]
        if len(tokens) != len(set(tokens)) or len(originals) != len(set(originals)):
            raise ValueError("token mappings must be one-to-one")
        return self

    def as_session_mapping(self) -> dict[str, str]:
        """Return the serializable token-to-original shape used by SessionState."""

        return {entry.token: entry.original_value for entry in self.token_mappings}
