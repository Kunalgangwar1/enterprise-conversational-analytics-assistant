"""Unit tests for typed session identity and state contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.chat_modes import ChatModeKey
from app.sessions.exceptions import InvalidTabIdError
from app.sessions.identity import SessionIdentity, resolve_session_identity
from app.sessions.models import SessionState


def test_default_session_state_has_empty_auto_conversation() -> None:
    state = SessionState(
        browser_session_id=str(uuid4()),
        tab_id="default",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert state.selected_mode is ChatModeKey.AUTO
    assert state.chat_history == []
    assert state.last_generated_sql is None
    assert state.last_token_mapping is None
    assert state.follow_up_questions == []


def test_request_scoped_fields_are_not_part_of_persisted_state() -> None:
    assert "token_mapping_history" not in SessionState.model_fields
    assert "custom_context" not in SessionState.model_fields


def test_session_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        SessionState(
            browser_session_id=str(uuid4()),
            tab_id="default",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_invalid_browser_cookie_is_replaced_with_uuid4() -> None:
    resolved = resolve_session_identity("../../unsafe", None)

    assert resolved.is_new_browser_session is True
    assert resolved.identity.tab_id == "default"
    assert SessionIdentity.model_validate(resolved.identity).browser_session_id


def test_invalid_tab_header_fails_validation() -> None:
    with pytest.raises(InvalidTabIdError):
        resolve_session_identity(None, "../../another-directory")
