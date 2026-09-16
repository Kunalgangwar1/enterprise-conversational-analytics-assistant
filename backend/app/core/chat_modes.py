"""Canonical top-level chat-mode configuration and lookup registry."""

from collections.abc import Iterable
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatModeKey(StrEnum):
    """Stable keys for user-selectable top-level product modes."""

    AUTO = "auto"
    SQL = "sql"
    GROUP_ACCESS = "group_access"
    DATA_DISCOVERY = "data_discovery"
    KNOWLEDGE_CATALOG = "knowledge_catalog"
    SEMANTICA = "semantica"
    DATA_QUALITY = "data_quality"


class ChatModeConfig(BaseModel):
    """Static product contract for a canonical chat mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: ChatModeKey
    display_name: NonBlankString
    description: NonBlankString
    welcome_message: NonBlankString


class UnsupportedChatModeError(ValueError):
    """Raised when a supplied mode is not part of the canonical registry."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        super().__init__(f"Unsupported chat mode: {mode}")


class ChatModeRegistry:
    """Immutable, deterministic registry of canonical chat-mode contracts."""

    def __init__(self, modes: Iterable[ChatModeConfig]) -> None:
        ordered_modes = tuple(modes)
        modes_by_key: dict[ChatModeKey, ChatModeConfig] = {}
        for mode in ordered_modes:
            if mode.key in modes_by_key:
                raise ValueError(f"Duplicate chat mode: {mode.key}")
            modes_by_key[mode.key] = mode
        self._ordered_modes = ordered_modes
        self._modes_by_key = MappingProxyType(modes_by_key)

    def get(self, mode: ChatModeKey | str) -> ChatModeConfig:
        """Resolve a canonical mode or raise a controlled domain error."""

        raw_mode = mode.value if isinstance(mode, ChatModeKey) else mode
        try:
            mode_key = ChatModeKey(raw_mode.strip().lower())
            return self._modes_by_key[mode_key]
        except (KeyError, ValueError):
            raise UnsupportedChatModeError(raw_mode) from None

    def list_modes(self) -> tuple[ChatModeConfig, ...]:
        """Return modes in their stable product-defined order."""

        return self._ordered_modes

    def is_supported(self, mode: ChatModeKey | str) -> bool:
        """Return whether a value resolves to a canonical mode."""

        try:
            self.get(mode)
        except UnsupportedChatModeError:
            return False
        return True


CANONICAL_CHAT_MODES = (
    ChatModeConfig(
        key=ChatModeKey.AUTO,
        display_name="Enterprise AI",
        description="A future entry point for selecting the appropriate enterprise capability.",
        welcome_message=(
            "This mode is intended to guide requests to the appropriate enterprise capability."
        ),
    ),
    ChatModeConfig(
        key=ChatModeKey.SQL,
        display_name="Data Intelligence",
        description="A future mode for exploring governed enterprise data with natural language.",
        welcome_message=(
            "This mode is intended for natural-language questions about governed analytical data."
        ),
    ),
    ChatModeConfig(
        key=ChatModeKey.GROUP_ACCESS,
        display_name="Data Access Assistant",
        description="A future mode for understanding data-access processes and requirements.",
        welcome_message=(
            "This mode is intended to help users understand data-access processes and requirements."
        ),
    ),
    ChatModeConfig(
        key=ChatModeKey.DATA_DISCOVERY,
        display_name="Data Discovery",
        description="A future mode for finding relevant enterprise datasets and data products.",
        welcome_message=(
            "This mode is intended for discovering relevant enterprise datasets and data products."
        ),
    ),
    ChatModeConfig(
        key=ChatModeKey.KNOWLEDGE_CATALOG,
        display_name="Knowledge Catalog",
        description="A future mode for locating governed organizational knowledge.",
        welcome_message=(
            "This mode is intended for locating governed organizational knowledge and guidance."
        ),
    ),
    ChatModeConfig(
        key=ChatModeKey.SEMANTICA,
        display_name="Semantica",
        description="A future mode for exploring shared business terminology and meaning.",
        welcome_message=(
            "This mode is intended for exploring shared business terminology and semantic meaning."
        ),
    ),
    ChatModeConfig(
        key=ChatModeKey.DATA_QUALITY,
        display_name="Data Quality",
        description="A future mode for understanding governed data-quality information.",
        welcome_message=(
            "This mode is intended for understanding governed data-quality information."
        ),
    ),
)

chat_mode_registry = ChatModeRegistry(CANONICAL_CHAT_MODES)
