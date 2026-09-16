"""Tests for strict, immutable route-eligibility configuration."""

from pathlib import Path

import pytest

from app.routing.exceptions import RoutingConfigurationError, RoutingUnavailableError
from app.routing.models import InternalRoute
from app.routing.registry import load_agent_registry


def _registry_yaml(*, disabled: InternalRoute | None = None) -> str:
    lines = ["agents:"]
    for route in InternalRoute:
        enabled = "false" if route is disabled else "true"
        lines.extend((f"  {route.value}:", f"    enabled: {enabled}"))
    return "\n".join(lines) + "\n"


def test_default_registry_loads_every_route_in_deterministic_order() -> None:
    registry = load_agent_registry()

    assert registry.list_enabled() == tuple(InternalRoute)
    assert all(registry.is_enabled(route) for route in InternalRoute)


def test_disabled_route_is_recognized_and_required_route_fails(tmp_path: Path) -> None:
    path = tmp_path / "agents.yaml"
    path.write_text(_registry_yaml(disabled=InternalRoute.SEMANTICA), encoding="utf-8")

    registry = load_agent_registry(path)

    assert registry.is_enabled(InternalRoute.SEMANTICA) is False
    assert InternalRoute.SEMANTICA not in registry.list_enabled()
    with pytest.raises(RoutingUnavailableError, match="semantica"):
        registry.require_enabled(InternalRoute.SEMANTICA)


def test_missing_registry_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(RoutingConfigurationError, match="not found"):
        load_agent_registry(tmp_path / "missing.yaml")


@pytest.mark.parametrize(
    "payload",
    [
        "agents: [unterminated",
        "agents:\n  sql:\n    enabled: yes\n",
        "agents:\n  unsupported_route:\n    enabled: true\n",
    ],
)
def test_malformed_or_incomplete_registry_fails_clearly(
    tmp_path: Path,
    payload: str,
) -> None:
    path = tmp_path / "agents.yaml"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(RoutingConfigurationError):
        load_agent_registry(path)
