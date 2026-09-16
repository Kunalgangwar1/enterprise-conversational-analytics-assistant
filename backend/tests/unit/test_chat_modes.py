"""Unit tests for canonical chat-mode configuration and lookup."""

import pytest

from app.core.chat_modes import (
    CANONICAL_CHAT_MODES,
    ChatModeKey,
    UnsupportedChatModeError,
    chat_mode_registry,
)

EXPECTED_MODE_ORDER = [
    "auto",
    "sql",
    "group_access",
    "data_discovery",
    "knowledge_catalog",
    "semantica",
    "data_quality",
]


def test_registry_contains_all_canonical_modes_in_deterministic_order() -> None:
    mode_keys = [mode.key.value for mode in chat_mode_registry.list_modes()]

    assert mode_keys == EXPECTED_MODE_ORDER
    assert len(CANONICAL_CHAT_MODES) == 7


def test_forecasting_is_not_a_top_level_mode() -> None:
    assert not chat_mode_registry.is_supported("forecasting")
    assert "forecasting" not in [mode.key.value for mode in chat_mode_registry.list_modes()]


def test_unknown_mode_lookup_fails_clearly() -> None:
    with pytest.raises(UnsupportedChatModeError, match="Unsupported chat mode: magic_ai"):
        chat_mode_registry.get("magic_ai")


def test_every_mode_has_complete_display_configuration() -> None:
    for mode in chat_mode_registry.list_modes():
        assert isinstance(mode.key, ChatModeKey)
        assert mode.display_name.strip()
        assert mode.description.strip()
        assert mode.welcome_message.strip()
