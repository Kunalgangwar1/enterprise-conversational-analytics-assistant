"""Typed Semantica adjacency artifact."""

from pydantic import BaseModel, ConfigDict


class SemanticaGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adjacency: dict[str, tuple[str, ...]]
