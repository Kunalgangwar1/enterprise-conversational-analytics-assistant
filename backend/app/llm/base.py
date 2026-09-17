"""Provider-independent LLM client protocol."""

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.llm.models import LLMRequest, LLMResponse

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """Contract used by future application workflows."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a provider-neutral plain-text response."""

        ...

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        """Generate and validate a typed structured result."""

        ...

    def close(self) -> None:
        """Release provider transport resources."""

        ...
