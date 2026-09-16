"""Typed internal routing contracts."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.chat_modes import ChatModeKey

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RoutingModel(BaseModel):
    """Strict immutable base model for routing values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class InternalRoute(StrEnum):
    """Complete set of specialist routes known to the clean-room supervisor."""

    GROUP_ACCESS = "group_access"
    SQL = "sql"
    FORECASTING = "forecasting"
    CHAT = "chat"
    HELP = "help"
    DATA_DISCOVERY = "data_discovery"
    KNOWLEDGE_CATALOG = "knowledge_catalog"
    SEMANTICA = "semantica"
    DATA_QUALITY = "data_quality"


class RoutingSource(StrEnum):
    """Policy source that produced the final route decision."""

    FORCED_MODE = "forced_mode"
    HEURISTIC = "heuristic"
    LLM = "llm"
    FALLBACK = "fallback"


class LLMIntentDecision(RoutingModel):
    """Validated structured result requested from the intent classifier."""

    intent: InternalRoute
    confidence: float = Field(ge=0, le=1)


class SupervisorDecision(RoutingModel):
    """Final internal routing decision without specialist execution."""

    route: InternalRoute
    confidence: float = Field(ge=0, le=1)
    source: RoutingSource
    selected_mode: ChatModeKey
    reason_code: NonBlankString | None = None
