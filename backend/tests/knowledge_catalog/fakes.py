"""Network-free fakes for catalog retrieval tests."""

import hashlib
import math
import re

from app.knowledge_catalog.models import RetrievalResult


class FakeEmbeddingClient:
    """Deterministic token-hash embeddings with a stable fixed dimension."""

    provider_name = "test_fake"
    model_name = "stable-hash-v1"

    def __init__(self, dimensions: int = 16) -> None:
        self.dimensions = dimensions
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        aliases = {
            "reimbursement": "claim",
            "eligible": "allowed_amount",
            "schedule": "appointment",
            "scheduling": "appointment",
            "clinician": "provider",
        }
        vector = [0.0] * self.dimensions
        words = re.findall(r"[a-z0-9_]+", text.lower())
        for word in words:
            normalized = aliases.get(word, word)
            digest = hashlib.sha256(normalized.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:2], "big") % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class StubRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def retrieve(self, safe_question: str) -> RetrievalResult:
        self.calls.append(safe_question)
        return self.result
