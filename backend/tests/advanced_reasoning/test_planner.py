"""Bounded planner graph, allow-list, dependency, and reflection tests."""

import pytest

from app.advanced_reasoning.exceptions import (
    AdvancedReasoningCitationError,
    AdvancedReasoningPlanError,
    AdvancedToolUnavailableError,
)
from app.advanced_reasoning.graph import ADVANCED_REASONING_NODE_SEQUENCE
from app.advanced_reasoning.planner import AdvancedReasoningPlanner
from app.routing.models import InternalRoute
from tests.advanced_reasoning.helpers import RecordingTool, supervisor_decision, tool_registry
from tests.llm.fakes import FakeLLMClient


def _base_payloads(tool_name: str = "sql") -> list[dict[str, object]]:
    return [
        {"subtasks": [{"task_id": "task-1", "description": "Find the answer"}]},
        {
            "steps": [
                {
                    "step_id": "step-1",
                    "tool_name": tool_name,
                    "instruction": "Find the answer",
                    "depends_on": [],
                }
            ]
        },
        {"status": "sufficient", "missing_information": [], "suggested_additional_tasks": []},
        {"answer": "Grounded final answer.", "citation_ids": [f"citation-{tool_name}"]},
    ]


def test_graph_contains_required_nodes_and_synthesizes() -> None:
    calls: list[str] = []
    fake = FakeLLMClient(structured_payloads=_base_payloads())
    planner = AdvancedReasoningPlanner(
        fake,
        tool_registry(RecordingTool("sql", InternalRoute.SQL, calls)),
    )

    result = planner.run("Safe analytical question", supervisor_decision())

    graph_nodes = set(planner.graph.get_graph().nodes)
    assert set(ADVANCED_REASONING_NODE_SEQUENCE) <= graph_nodes
    assert calls == ["sql"]
    assert result.answer == "Grounded final answer."
    assert result.citations == ("citation-sql",)
    assert "chain-of-thought" not in result.answer


def test_planner_can_execute_injected_forecasting_tool() -> None:
    calls: list[str] = []
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=_base_payloads("forecasting")),
        tool_registry(RecordingTool("forecasting", InternalRoute.FORECASTING, calls)),
    )

    result = planner.run(
        "Forecast aggregate monthly claims",
        supervisor_decision(route=InternalRoute.FORECASTING),
    )

    assert calls == ["forecasting"]
    assert result.citations == ("citation-forecasting",)


@pytest.mark.parametrize("tool_name", ["shell", "python", "https://example.test"])
def test_unknown_or_unimplemented_tools_cannot_execute(tool_name: str) -> None:
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=_base_payloads(tool_name)),
        tool_registry(RecordingTool("sql", InternalRoute.SQL, [])),
    )

    with pytest.raises(AdvancedToolUnavailableError):
        planner.run("Safe question", supervisor_decision())


def test_disabled_tool_cannot_execute() -> None:
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=_base_payloads()),
        tool_registry(
            RecordingTool("sql", InternalRoute.SQL, []),
            enabled_names=set(),
        ),
    )

    with pytest.raises(AdvancedToolUnavailableError):
        planner.run("Safe question", supervisor_decision())


@pytest.mark.parametrize(
    "instruction",
    ["SELECT * FROM claims", "curl https://example.test", "https://example.test/data"],
)
def test_executable_planner_instructions_are_rejected(instruction: str) -> None:
    payloads = _base_payloads()
    payloads[1]["steps"][0]["instruction"] = instruction
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=payloads),
        tool_registry(RecordingTool("sql", InternalRoute.SQL, [])),
    )

    with pytest.raises(AdvancedReasoningPlanError, match="executable"):
        planner.run("Safe question", supervisor_decision())


def test_dependency_order_is_topological_not_model_order() -> None:
    calls: list[str] = []
    payloads = _base_payloads()
    payloads[1] = {
        "steps": [
            {
                "step_id": "step-2",
                "tool_name": "knowledge_catalog",
                "instruction": "Second",
                "depends_on": ["step-1"],
            },
            {
                "step_id": "step-1",
                "tool_name": "sql",
                "instruction": "First",
                "depends_on": [],
            },
        ]
    }
    payloads[3] = {
        "answer": "Combined answer.",
        "citation_ids": ["citation-sql", "citation-knowledge_catalog"],
    }
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=payloads),
        tool_registry(
            RecordingTool("sql", InternalRoute.SQL, calls),
            RecordingTool("knowledge_catalog", InternalRoute.KNOWLEDGE_CATALOG, calls),
        ),
    )

    planner.run("Safe question", supervisor_decision())

    assert calls == ["sql", "knowledge_catalog"]


def test_subtask_and_tool_call_budgets_are_enforced() -> None:
    payloads = _base_payloads()
    payloads[0] = {
        "subtasks": [
            {"task_id": "task-1", "description": "One"},
            {"task_id": "task-2", "description": "Two"},
        ]
    }
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=payloads),
        tool_registry(RecordingTool("sql", InternalRoute.SQL, [])),
        max_subtasks=1,
    )

    with pytest.raises(AdvancedReasoningPlanError, match="subtask budget"):
        planner.run("Safe question", supervisor_decision())

    tool_payloads = _base_payloads()
    tool_payloads[1] = {
        "steps": [
            {
                "step_id": "step-1",
                "tool_name": "sql",
                "instruction": "One",
                "depends_on": [],
            },
            {
                "step_id": "step-2",
                "tool_name": "sql",
                "instruction": "Two",
                "depends_on": [],
            },
        ]
    }
    tool_limited = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=tool_payloads),
        tool_registry(RecordingTool("sql", InternalRoute.SQL, [])),
        max_tool_calls=1,
    )
    with pytest.raises(AdvancedReasoningPlanError, match="tool-call budget"):
        tool_limited.run("Safe question", supervisor_decision())


def test_needs_more_replans_once_then_synthesizes_with_warning() -> None:
    calls: list[str] = []
    payloads = [
        {"subtasks": [{"task_id": "task-1", "description": "Initial"}]},
        {
            "steps": [
                {
                    "step_id": "step-1",
                    "tool_name": "sql",
                    "instruction": "Initial",
                    "depends_on": [],
                }
            ]
        },
        {
            "status": "needs_more",
            "missing_information": ["Catalog meaning"],
            "suggested_additional_tasks": ["Look up meaning"],
        },
        {
            "steps": [
                {
                    "step_id": "step-2",
                    "tool_name": "knowledge_catalog",
                    "instruction": "Look up meaning",
                    "depends_on": ["step-1"],
                }
            ]
        },
        {
            "status": "needs_more",
            "missing_information": ["Unavailable"],
            "suggested_additional_tasks": ["Keep looping"],
        },
        {
            "answer": "Bounded partial answer.",
            "citation_ids": ["citation-sql", "citation-knowledge_catalog"],
        },
    ]
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=payloads),
        tool_registry(
            RecordingTool("sql", InternalRoute.SQL, calls),
            RecordingTool("knowledge_catalog", InternalRoute.KNOWLEDGE_CATALOG, calls),
        ),
        max_replans=1,
    )

    result = planner.run("Safe question", supervisor_decision())

    assert calls == ["sql", "knowledge_catalog"]
    assert len(result.warnings) == 1


def test_tool_budget_exhaustion_synthesizes_limited_evidence_without_looping() -> None:
    calls: list[str] = []
    payloads = _base_payloads()
    payloads[2] = {
        "status": "needs_more",
        "missing_information": ["More data"],
        "suggested_additional_tasks": ["Run another tool"],
    }
    payloads[3] = {"answer": "Limited answer.", "citation_ids": ["citation-sql"]}
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=payloads),
        tool_registry(RecordingTool("sql", InternalRoute.SQL, calls)),
        max_tool_calls=1,
    )

    result = planner.run("Safe question", supervisor_decision())

    assert calls == ["sql"]
    assert result.answer == "Limited answer."
    assert len(result.warnings) == 1


def test_synthesis_cannot_invent_citation() -> None:
    payloads = _base_payloads()
    payloads[3] = {"answer": "Claim.", "citation_ids": ["invented"]}
    planner = AdvancedReasoningPlanner(
        FakeLLMClient(structured_payloads=payloads),
        tool_registry(RecordingTool("sql", InternalRoute.SQL, [])),
    )

    with pytest.raises(AdvancedReasoningCitationError):
        planner.run("Safe question", supervisor_decision())
