"""Typed immutable loading for internal route eligibility."""

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.routing.exceptions import RoutingConfigurationError, RoutingUnavailableError
from app.routing.models import InternalRoute

_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "agents_registry.yaml"


class AgentAvailability(BaseModel):
    """Eligibility configuration for one internal route."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    enabled: bool


class AgentRegistryConfig(BaseModel):
    """Strict file contract requiring every internal route exactly once."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agents: dict[InternalRoute, AgentAvailability]

    @model_validator(mode="after")
    def require_all_internal_routes(self) -> Self:
        configured = set(self.agents)
        expected = set(InternalRoute)
        if configured != expected:
            raise ValueError("agent registry must represent every internal route exactly once")
        return self


class AgentRegistry:
    """Read-only deterministic view of route eligibility."""

    def __init__(self, availability: Mapping[InternalRoute, AgentAvailability]) -> None:
        self._availability = MappingProxyType(dict(availability))

    def is_enabled(self, route: InternalRoute) -> bool:
        """Return whether a route is eligible for supervisor selection."""

        return self._availability[route].enabled

    def require_enabled(self, route: InternalRoute) -> None:
        """Raise a controlled error when a required route is unavailable."""

        if not self.is_enabled(route):
            raise RoutingUnavailableError(f"Internal route '{route.value}' is disabled")

    def list_enabled(self) -> tuple[InternalRoute, ...]:
        """Return enabled routes in stable enum order."""

        return tuple(route for route in InternalRoute if self.is_enabled(route))


def load_agent_registry(path: Path = _DEFAULT_REGISTRY_PATH) -> AgentRegistry:
    """Load and validate route eligibility from YAML without permissive defaults."""

    try:
        raw_config = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RoutingConfigurationError(f"Agent registry file not found: {path}") from exc
    except OSError as exc:
        raise RoutingConfigurationError(f"Agent registry file could not be read: {path}") from exc

    try:
        payload = yaml.safe_load(raw_config)
    except yaml.YAMLError as exc:
        raise RoutingConfigurationError("Malformed YAML in agent registry") from exc

    try:
        config = AgentRegistryConfig.model_validate(payload)
    except ValidationError as exc:
        raise RoutingConfigurationError("Invalid agent registry configuration") from exc
    return AgentRegistry(config.agents)


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    """Load and cache the immutable default registry."""

    return load_agent_registry()
