"""Unit tests for safe atomic JSON session persistence."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.chat_modes import ChatModeKey
from app.sessions.exceptions import SessionStoreError
from app.sessions.identity import (
    SessionIdentity,
    derive_session_storage_key,
)
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import ChatMessage, ChatRole, SessionState


def _identity(tab_id: str = "tab-a") -> SessionIdentity:
    return SessionIdentity(browser_session_id=str(uuid4()), tab_id=tab_id)


def _state(identity: SessionIdentity) -> SessionState:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return SessionState(
        browser_session_id=identity.browser_session_id,
        tab_id=identity.tab_id,
        selected_mode=ChatModeKey.SQL,
        chat_history=[
            ChatMessage(role=ChatRole.USER, content="Synthetic test question", created_at=timestamp)
        ],
        last_generated_sql="SELECT 1",
        last_token_mapping={"synthetic": "TOKEN_1"},
        follow_up_questions=["Synthetic follow-up?"],
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_storage_key_is_deterministic_and_tab_specific() -> None:
    browser_id = str(uuid4())

    first = derive_session_storage_key(browser_id, "tab-a")
    repeated = derive_session_storage_key(browser_id, "tab-a")
    other_tab = derive_session_storage_key(browser_id, "tab-b")

    assert first == repeated
    assert first != other_tab
    assert len(first) == 64
    assert set(first).issubset(set("0123456789abcdef"))


def test_path_traversal_like_input_can_only_produce_safe_hash_path(tmp_path: Path) -> None:
    storage_key = derive_session_storage_key(str(uuid4()), "../../outside/session")
    candidate = tmp_path / f"session_{storage_key}.json"

    assert candidate.parent == tmp_path
    assert candidate.name == f"session_{storage_key}.json"
    assert ".." not in candidate.name
    assert "/" not in candidate.name


def test_save_load_round_trip_and_final_file_is_valid_json(tmp_path: Path) -> None:
    store = JsonFileSessionStore(tmp_path)
    identity = _identity()
    state = _state(identity)

    store.save(state)

    assert store.load(identity) == state
    payload = json.loads(store.path_for(identity).read_text(encoding="utf-8"))
    assert payload["selected_mode"] == "sql"
    assert payload["chat_history"][0]["role"] == "user"
    assert list(tmp_path.glob("*.tmp")) == []


def test_corrupted_json_raises_and_is_not_silently_overwritten(tmp_path: Path) -> None:
    store = JsonFileSessionStore(tmp_path)
    identity = _identity()
    path = store.path_for(identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid JSON", encoding="utf-8")

    with pytest.raises(SessionStoreError, match="corrupted"):
        store.load(identity)
    with pytest.raises(SessionStoreError, match="corrupted"):
        store.save(_state(identity))

    assert path.read_text(encoding="utf-8") == "{not valid JSON"
