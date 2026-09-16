"""API tests for stateful mode selection, reset, cookies, and tab isolation."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.chat_modes import ChatModeKey
from app.core.config import Settings
from app.main import create_app
from app.sessions.identity import SessionIdentity
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import ChatMessage, ChatRole


@dataclass(frozen=True)
class SessionAPIContext:
    client: TestClient
    store: JsonFileSessionStore
    settings: Settings


@pytest.fixture
def session_api(tmp_path: Path) -> Iterator[SessionAPIContext]:
    settings = Settings(
        app_name="Test Analytics API",
        app_env="test",
        artifacts_output_dir=tmp_path,
    )
    store = JsonFileSessionStore(tmp_path / "sessions")
    application = create_app(settings, session_store=store)
    with TestClient(application) as client:
        yield SessionAPIContext(client=client, store=store, settings=settings)


def test_select_mode_sets_secure_local_cookie_contract_and_keeps_it_stable(
    session_api: SessionAPIContext,
) -> None:
    first_response = session_api.client.post(
        "/chat/select-mode",
        headers={"X-Tab-Id": "tab-a"},
        json={"mode": "sql"},
    )

    assert first_response.status_code == 200
    assert first_response.json() == {
        "mode": "sql",
        "display_name": "Data Intelligence",
    }
    browser_session_id = session_api.client.cookies.get(session_api.settings.session_cookie_name)
    assert browser_session_id
    set_cookie = first_response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert f"max-age={session_api.settings.session_max_age_seconds}" in set_cookie

    second_response = session_api.client.post(
        "/chat/reset",
        headers={"X-Tab-Id": "tab-a"},
    )

    assert second_response.status_code == 200
    assert (
        session_api.client.cookies.get(session_api.settings.session_cookie_name)
        == browser_session_id
    )
    assert "set-cookie" not in second_response.headers


def test_select_mode_rejects_unknown_mode_with_existing_error_contract(
    session_api: SessionAPIContext,
) -> None:
    response = session_api.client.post(
        "/chat/select-mode",
        json={"mode": "magic_ai"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "invalid_chat_mode",
            "message": "Unsupported chat mode: magic_ai",
        }
    }


def test_mode_selection_and_reset_are_isolated_by_tab(
    session_api: SessionAPIContext,
) -> None:
    tab_a_response = session_api.client.post(
        "/chat/select-mode",
        headers={"X-Tab-Id": "tab-a"},
        json={"mode": "sql"},
    )
    tab_b_response = session_api.client.post(
        "/chat/select-mode",
        headers={"X-Tab-Id": "tab-b"},
        json={"mode": "data_quality"},
    )
    assert tab_a_response.status_code == 200
    assert tab_b_response.status_code == 200

    browser_session_id = session_api.client.cookies.get(session_api.settings.session_cookie_name)
    assert browser_session_id is not None
    tab_a = SessionIdentity(browser_session_id=browser_session_id, tab_id="tab-a")
    tab_b = SessionIdentity(browser_session_id=browser_session_id, tab_id="tab-b")
    state_a = session_api.store.load(tab_a)
    state_b = session_api.store.load(tab_b)
    assert state_a is not None
    assert state_b is not None
    assert state_a.selected_mode is ChatModeKey.SQL
    assert state_b.selected_mode is ChatModeKey.DATA_QUALITY

    session_api.store.save(
        state_a.model_copy(
            update={
                "chat_history": [
                    ChatMessage(role=ChatRole.USER, content="Synthetic tab A question")
                ],
                "last_generated_sql": "SELECT 1",
            }
        )
    )
    session_api.store.save(
        state_b.model_copy(update={"follow_up_questions": ["Synthetic tab B follow-up?"]})
    )

    reset_response = session_api.client.post(
        "/chat/reset",
        headers={"X-Tab-Id": "tab-a"},
    )

    assert reset_response.status_code == 200
    assert reset_response.json() == {"status": "reset", "mode": "sql"}
    reset_a = session_api.store.load(tab_a)
    untouched_b = session_api.store.load(tab_b)
    assert reset_a is not None
    assert untouched_b is not None
    assert reset_a.chat_history == []
    assert reset_a.last_generated_sql is None
    assert reset_a.selected_mode is ChatModeKey.SQL
    assert untouched_b.selected_mode is ChatModeKey.DATA_QUALITY
    assert untouched_b.follow_up_questions == ["Synthetic tab B follow-up?"]


def test_absent_tab_header_uses_default_tab(session_api: SessionAPIContext) -> None:
    response = session_api.client.post(
        "/chat/select-mode",
        json={"mode": "auto"},
    )

    assert response.status_code == 200
    browser_session_id = session_api.client.cookies.get(session_api.settings.session_cookie_name)
    assert browser_session_id is not None
    state = session_api.store.load(
        SessionIdentity(browser_session_id=browser_session_id, tab_id="default")
    )
    assert state is not None
    assert state.selected_mode is ChatModeKey.AUTO


def test_invalid_tab_header_is_rejected_without_writing_state(
    session_api: SessionAPIContext,
) -> None:
    response = session_api.client.post(
        "/chat/select-mode",
        headers={"X-Tab-Id": "../../outside"},
        json={"mode": "sql"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_tab_id"
    assert list(session_api.store.session_directory.glob("*.json")) == []
