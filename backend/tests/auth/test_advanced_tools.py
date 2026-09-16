"""Permission-filtered advanced tool registry tests."""

import pytest

from app.advanced_reasoning.exceptions import AdvancedToolUnavailableError
from app.advanced_reasoning.models import ToolPlanStep
from app.auth.roles import AppRole
from app.routing.models import InternalRoute
from tests.advanced_reasoning.helpers import RecordingTool, tool_registry
from tests.auth.helpers import principal


def test_viewer_registry_excludes_sql_and_forecasting_before_planning() -> None:
    calls: list[str] = []
    registry = tool_registry(
        RecordingTool("sql", InternalRoute.SQL, calls),
        RecordingTool("forecasting", InternalRoute.FORECASTING, calls),
        RecordingTool("knowledge_catalog", InternalRoute.KNOWLEDGE_CATALOG, calls),
    ).authorized(principal(AppRole.VIEWER).permissions)

    assert registry.available_names() == ("knowledge_catalog",)
    assert all(not item.startswith("sql:") for item in registry.descriptions())

    with pytest.raises(AdvancedToolUnavailableError):
        registry.execute(
            ToolPlanStep(step_id="malicious", tool_name="sql", instruction="Count claims")
        )
    assert calls == []


def test_analyst_registry_includes_privileged_tools() -> None:
    calls: list[str] = []
    registry = tool_registry(
        RecordingTool("sql", InternalRoute.SQL, calls),
        RecordingTool("forecasting", InternalRoute.FORECASTING, calls),
    ).authorized(principal(AppRole.ANALYST).permissions)
    assert registry.available_names() == ("forecasting", "sql")
