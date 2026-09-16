"""Network-free evaluation doubles implementing provider-neutral protocols."""

import hashlib
import math
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.llm.base import StructuredModel
from app.llm.models import LLMRequest, LLMResponse


class ModelPayloadLLM:
    """Return deterministic payloads selected by structured response model."""

    def __init__(
        self, payloads: dict[type[BaseModel], dict[str, Any] | list[dict[str, Any]]]
    ) -> None:
        self._payloads = payloads
        self._positions: dict[type[BaseModel], int] = {}
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            text="evaluation fake", provider="evaluation_fake", model="fixed", elapsed_ms=0
        )

    def generate_structured(
        self, request: LLMRequest, response_model: type[StructuredModel]
    ) -> StructuredModel:
        self.requests.append(request)
        configured = self._payloads[response_model]
        if isinstance(configured, list):
            position = self._positions.get(response_model, 0)
            if position >= len(configured):
                raise AssertionError(f"No fake response remains for {response_model.__name__}")
            payload = configured[position]
            self._positions[response_model] = position + 1
        else:
            payload = configured
        return response_model.model_validate(payload)


class FixedEmbeddingClient:
    provider_name = "evaluation_fake"
    model_name = "fixed-v1"
    dimensions = 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class HashEmbeddingClient:
    """Deterministic token-hash embeddings for temporary integration indexes."""

    provider_name = "evaluation_fake"
    model_name = "stable-hash-v1"

    def __init__(self, dimensions: int = 16) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        aliases = {
            "clinician": "provider",
            "eligible": "allowed_amount",
            "reimbursement": "claim",
            "schedule": "appointment",
            "scheduling": "appointment",
        }
        vector = [0.0] * self.dimensions
        for word in re.findall(r"[a-z0-9_]+", text.lower()):
            normalized = aliases.get(word, word)
            digest = hashlib.sha256(normalized.encode()).digest()
            vector[int.from_bytes(digest[:2], "big") % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class StaticTool:
    def __init__(self, name: str, route: Any, execute: Callable[[str], Any] | None = None) -> None:
        self.name = name
        self.route = route
        self.description = f"Evaluation-only {name} adapter"
        self._execute = execute

    def execute(self, instruction: str) -> Any:
        if self._execute is None:
            raise RuntimeError("Static evaluation tool execution was not configured")
        return self._execute(instruction)
