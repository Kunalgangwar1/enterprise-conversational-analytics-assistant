"""Small deterministic builders shared by routing tests."""

from app.routing.models import InternalRoute
from app.routing.registry import AgentAvailability, AgentRegistry


def make_registry(**overrides: bool) -> AgentRegistry:
    """Build a complete in-memory registry with selected route overrides."""

    unknown = set(overrides) - {route.value for route in InternalRoute}
    if unknown:
        raise ValueError("Unknown test route override")
    return AgentRegistry(
        {
            route: AgentAvailability(enabled=overrides.get(route.value, True))
            for route in InternalRoute
        }
    )
