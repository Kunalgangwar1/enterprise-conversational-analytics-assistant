"""Stable public and internal contracts for the unified chat endpoint."""

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.auth.group_access import GroupAccessResult
from app.core.chat_modes import ChatModeKey
from app.data_discovery.models import DataDiscoveryResult
from app.forecasting.models import ForecastResult
from app.nlp2sql.multihop.models import DeltaAnnotation, SynthesisTable
from app.privacy.models import TokenMappingEntry
from app.routing.models import InternalRoute
from app.security.request_limits import ChatMessageText, CustomContextText


class SQLStrategy(StrEnum):
    AUTO = "auto"
    STANDARD = "standard"
    ADVANCED = "advanced"
    FORECASTING = "forecasting"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: ChatMessageText
    sql_strategy: SQLStrategy | None = None
    custom_context: CustomContextText | None = None


class ChatCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    section: str | None = None
    source_path: str


class SQLChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sql: str
    status: Literal["ready_to_execute"] = "ready_to_execute"
    selected_domains: tuple[str, ...]
    selected_tables: tuple[str, ...]


class RAGChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieval_method: str | None = None
    citations: tuple[ChatCitation, ...] = ()


class AdvancedChatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    table: SynthesisTable = Field(default_factory=SynthesisTable)
    deltas: tuple[DeltaAnnotation, ...] = ()


class ChatResponseBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: UUID = Field(default_factory=uuid4)
    selected_mode: ChatModeKey
    route: InternalRoute
    content: str
    follow_up_questions: tuple[str, ...] = ()
    latency_ms: float = Field(ge=0)


class MessageChatResponse(ChatResponseBase):
    response_type: Literal["message"] = "message"
    payload: None = None


class SQLChatResponse(ChatResponseBase):
    response_type: Literal["sql"] = "sql"
    payload: SQLChatPayload


class DiscoveryChatResponse(ChatResponseBase):
    response_type: Literal["data_discovery"] = "data_discovery"
    payload: DataDiscoveryResult


class RAGChatResponse(ChatResponseBase):
    response_type: Literal["knowledge_catalog", "data_quality", "semantica"]
    payload: RAGChatPayload


class AdvancedChatResponse(ChatResponseBase):
    response_type: Literal["advanced"] = "advanced"
    payload: AdvancedChatPayload


class ForecastChatResponse(ChatResponseBase):
    response_type: Literal["forecast"] = "forecast"
    payload: ForecastResult


class GroupAccessChatResponse(ChatResponseBase):
    response_type: Literal["group_access"] = "group_access"
    payload: GroupAccessResult


ChatResponse: TypeAlias = Annotated[
    MessageChatResponse
    | SQLChatResponse
    | DiscoveryChatResponse
    | RAGChatResponse
    | AdvancedChatResponse
    | ForecastChatResponse
    | GroupAccessChatResponse,
    Field(discriminator="response_type"),
]


class ChatTurnResult(BaseModel):
    """Internal response plus the only current-turn state permitted to persist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    response: ChatResponse
    token_mappings: tuple[TokenMappingEntry, ...] = ()
    accepted_sql: str | None = None
