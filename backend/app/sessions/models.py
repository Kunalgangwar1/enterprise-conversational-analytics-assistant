"""Typed persisted conversation-state contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.chat_modes import ChatModeKey
from app.sessions.identity import normalize_browser_session_id, validate_tab_id


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class ChatRole(StrEnum):
    """Conversation roles supported by the initial state contract."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """Minimal persisted user or assistant message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    role: ChatRole
    content: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        return _as_utc(value)


class SessionState(BaseModel):
    """Durable state isolated by authenticated subject, browser, and tab."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    browser_session_id: str
    tab_id: str
    owner_subject: str | None = None
    selected_mode: ChatModeKey = ChatModeKey.AUTO
    chat_history: list[ChatMessage] = Field(default_factory=list)
    last_generated_sql: str | None = None
    last_token_mapping: dict[str, str] | None = None
    follow_up_questions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # token_mapping_history is intentionally request-scoped and is not persisted.
    # custom_context will arrive with a future chat turn and is not durable session memory.

    @field_validator("browser_session_id")
    @classmethod
    def require_valid_browser_session_id(cls, value: str) -> str:
        return normalize_browser_session_id(value)

    @field_validator("tab_id")
    @classmethod
    def require_valid_tab_id(cls, value: str) -> str:
        return validate_tab_id(value)

    @field_validator("owner_subject")
    @classmethod
    def require_valid_owner_subject(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 512:
            raise ValueError("owner subject must contain 1-512 characters")
        return normalized

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_aware_timestamps(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @model_validator(mode="after")
    def require_ordered_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("session timestamps must be timezone-aware")
    return value.astimezone(UTC)
