"""Provider-neutral LLM request and response contracts."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LLMRole(StrEnum):
    """Text-message roles supported by the initial provider abstraction."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMProvider(StrEnum):
    """Real providers implemented by the production LLM package."""

    AZURE_OPENAI = "azure_openai"
    GEMINI = "gemini"


class LLMMessage(BaseModel):
    """Provider-neutral text message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: LLMRole
    content: NonBlankString


class LLMRequest(BaseModel):
    """Provider-neutral generation request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: list[LLMMessage] = Field(min_length=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)


class LLMUsage(BaseModel):
    """Optional token accounting returned by a provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class LLMResponse(BaseModel):
    """Provider-neutral text result without raw SDK objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: NonBlankString
    provider: NonBlankString
    model: NonBlankString
    request_id: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    elapsed_ms: float = Field(ge=0)
