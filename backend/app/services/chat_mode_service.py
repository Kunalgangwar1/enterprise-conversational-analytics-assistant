"""Service for resolving chat modes and preparing welcome responses."""

from pydantic import BaseModel, ConfigDict

from app.core.chat_modes import ChatModeKey, ChatModeRegistry, chat_mode_registry


class ChatModeWelcome(BaseModel):
    """Transport-neutral welcome data for a canonical chat mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ChatModeKey
    display_name: str
    description: str
    welcome_message: str


class ChatModeService:
    """Resolve configured modes without adding session or agent behavior."""

    def __init__(self, registry: ChatModeRegistry) -> None:
        self._registry = registry

    def get_welcome(self, mode: str) -> ChatModeWelcome:
        """Prepare a welcome response for a supplied canonical mode."""

        config = self._registry.get(mode)
        return ChatModeWelcome(
            mode=config.key,
            display_name=config.display_name,
            description=config.description,
            welcome_message=config.welcome_message,
        )


chat_mode_service = ChatModeService(chat_mode_registry)
