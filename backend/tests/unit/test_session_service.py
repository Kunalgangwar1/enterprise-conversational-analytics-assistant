"""Unit tests for session mutations and multi-tab isolation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.chat_modes import ChatModeKey, UnsupportedChatModeError, chat_mode_registry
from app.sessions.identity import SessionIdentity
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import ChatMessage, ChatRole
from app.sessions.service import SessionService


class IncrementingClock:
    """Small deterministic clock for state-transition tests."""

    def __init__(self) -> None:
        self._current = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self._current
        self._current += timedelta(seconds=1)
        return current


def _service(tmp_path: Path) -> tuple[SessionService, JsonFileSessionStore]:
    store = JsonFileSessionStore(tmp_path)
    service = SessionService(store, chat_mode_registry, clock=IncrementingClock())
    return service, store


def test_select_mode_reuses_canonical_registry_validation(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    identity = SessionIdentity(browser_session_id=str(uuid4()), tab_id="tab-a")

    selection = service.select_mode(identity, "sql")

    assert selection.mode is chat_mode_registry.get("sql")
    persisted = store.load(identity)
    assert persisted is not None
    assert persisted.selected_mode is ChatModeKey.SQL
    with pytest.raises(UnsupportedChatModeError):
        service.select_mode(identity, "invalid_mode")


def test_reset_clears_conversation_and_preserves_mode_and_creation(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    identity = SessionIdentity(browser_session_id=str(uuid4()), tab_id="tab-a")
    selected = service.select_mode(identity, "sql").state
    populated = selected.model_copy(
        update={
            "chat_history": [ChatMessage(role=ChatRole.USER, content="Synthetic question")],
            "last_generated_sql": "SELECT 1",
            "last_token_mapping": {"synthetic": "TOKEN_1"},
            "follow_up_questions": ["Synthetic follow-up?"],
        }
    )
    store.save(populated)

    reset_state = service.reset(identity)

    assert reset_state.chat_history == []
    assert reset_state.last_generated_sql is None
    assert reset_state.last_token_mapping is None
    assert reset_state.follow_up_questions == []
    assert reset_state.selected_mode is ChatModeKey.SQL
    assert reset_state.created_at == selected.created_at
    assert reset_state.updated_at > selected.updated_at


def test_tabs_are_independent_and_reset_affects_only_target_tab(tmp_path: Path) -> None:
    service, store = _service(tmp_path)
    browser_id = str(uuid4())
    tab_a = SessionIdentity(browser_session_id=browser_id, tab_id="tab-a")
    tab_b = SessionIdentity(browser_session_id=browser_id, tab_id="tab-b")

    state_a = service.select_mode(tab_a, "sql").state.model_copy(
        update={"last_generated_sql": "SELECT 1"}
    )
    state_b = service.select_mode(tab_b, "data_quality").state.model_copy(
        update={"follow_up_questions": ["Synthetic quality follow-up?"]}
    )
    store.save(state_a)
    store.save(state_b)

    service.reset(tab_a)

    reloaded_a = store.load(tab_a)
    reloaded_b = store.load(tab_b)
    assert reloaded_a is not None
    assert reloaded_b is not None
    assert reloaded_a.selected_mode is ChatModeKey.SQL
    assert reloaded_a.last_generated_sql is None
    assert reloaded_b.selected_mode is ChatModeKey.DATA_QUALITY
    assert reloaded_b.follow_up_questions == ["Synthetic quality follow-up?"]
