"""Safe browser and tab identity resolution for logical conversations."""

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, field_validator

from app.sessions.exceptions import InvalidTabIdError

DEFAULT_TAB_ID = "default"
MAX_TAB_ID_LENGTH = 64
_TAB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SessionIdentity(BaseModel):
    """Validated composite identity for one browser tab's conversation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    browser_session_id: str
    tab_id: str

    @field_validator("browser_session_id")
    @classmethod
    def validate_browser_session_id(cls, value: str) -> str:
        """Require an opaque UUID4 browser identifier."""

        return normalize_browser_session_id(value)

    @field_validator("tab_id")
    @classmethod
    def validate_tab_id_field(cls, value: str) -> str:
        """Require the constrained tab identifier syntax."""

        return validate_tab_id(value)


@dataclass(frozen=True)
class ResolvedSessionIdentity:
    """Resolved identity plus whether a new browser cookie is required."""

    identity: SessionIdentity
    is_new_browser_session: bool


def resolve_session_identity(
    browser_cookie: str | None,
    tab_header: str | None,
) -> ResolvedSessionIdentity:
    """Resolve or safely replace the browser ID and validate the tab ID."""

    is_new_browser_session = False
    try:
        browser_session_id = normalize_browser_session_id(browser_cookie or "")
    except ValueError:
        browser_session_id = str(uuid4())
        is_new_browser_session = True

    tab_id = DEFAULT_TAB_ID if tab_header is None else validate_tab_id(tab_header)
    return ResolvedSessionIdentity(
        identity=SessionIdentity(
            browser_session_id=browser_session_id,
            tab_id=tab_id,
        ),
        is_new_browser_session=is_new_browser_session,
    )


def normalize_browser_session_id(value: str) -> str:
    """Validate and canonicalize a UUID4 browser session identifier."""

    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("browser session ID must be a UUID4 value") from exc
    if parsed.version != 4:
        raise ValueError("browser session ID must be a UUID4 value")
    return str(parsed)


def validate_tab_id(value: str) -> str:
    """Validate a short opaque tab identifier without treating it as a path."""

    if not isinstance(value, str) or not _TAB_ID_PATTERN.fullmatch(value):
        raise InvalidTabIdError(
            "X-Tab-Id must be 1-64 characters using letters, numbers, '.', '_' or '-'"
        )
    return value


def derive_session_storage_key(browser_session_id: str, tab_id: str) -> str:
    """Derive a deterministic filename-safe key without exposing raw identifiers."""

    composite = (f"{len(browser_session_id)}:{browser_session_id}{len(tab_id)}:{tab_id}").encode()
    return hashlib.sha256(composite).hexdigest()
