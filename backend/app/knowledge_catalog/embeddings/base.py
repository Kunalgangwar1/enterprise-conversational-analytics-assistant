"""Provider-neutral embedding contract."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingClient(Protocol):
    """Small abstraction used by indexing and vector retrieval."""

    @property
    def provider_name(self) -> str:
        """Return a non-sensitive provider identifier for manifests."""

        ...

    @property
    def model_name(self) -> str:
        """Return the configured embedding model or deployment name."""

        ...

    @property
    def dimensions(self) -> int | None:
        """Return configured output dimensions when explicitly known."""

        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a non-empty batch of catalog chunks."""

        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed one retrieval query."""

        ...

    def close(self) -> None:
        """Release provider transport resources."""

        ...
