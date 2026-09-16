"""Authenticated-subject session isolation tests."""

from pathlib import Path
from uuid import uuid4

from app.core.chat_modes import chat_mode_registry
from app.sessions.identity import SessionIdentity
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import ChatMessage, ChatRole
from app.sessions.service import SessionService


def test_same_browser_and_tab_cannot_cross_authenticated_subjects(tmp_path: Path) -> None:
    store = JsonFileSessionStore(tmp_path)
    service = SessionService(store, chat_mode_registry)
    browser_id = str(uuid4())
    user_a = SessionIdentity(
        browser_session_id=browser_id,
        tab_id="shared-tab",
        owner_subject="user-a",
    )
    user_b = SessionIdentity(
        browser_session_id=browser_id,
        tab_id="shared-tab",
        owner_subject="user-b",
    )
    state_a = service.select_mode(user_a, "sql").state.model_copy(
        update={
            "chat_history": [ChatMessage(role=ChatRole.USER, content="Private A question")],
            "last_generated_sql": "SELECT 'user-a'",
            "last_token_mapping": {"T001": "A-secret"},
            "follow_up_questions": ["A-only follow-up"],
        }
    )
    store.save(state_a)

    state_b = service.get_or_create(user_b)

    assert store.path_for(user_a) != store.path_for(user_b)
    assert state_b.owner_subject == "user-b"
    assert state_b.chat_history == []
    assert state_b.last_generated_sql is None
    assert state_b.last_token_mapping is None
    assert state_b.follow_up_questions == []


def test_same_subject_still_has_per_tab_isolation(tmp_path: Path) -> None:
    store = JsonFileSessionStore(tmp_path)
    service = SessionService(store, chat_mode_registry)
    browser_id = str(uuid4())
    first = SessionIdentity(
        browser_session_id=browser_id,
        tab_id="tab-a",
        owner_subject="same-user",
    )
    second = SessionIdentity(
        browser_session_id=browser_id,
        tab_id="tab-b",
        owner_subject="same-user",
    )
    service.select_mode(first, "sql")
    assert service.get_or_create(second).selected_mode.value == "auto"
