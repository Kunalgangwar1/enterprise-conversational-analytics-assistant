"""Approved-tool selection, completion, and budget invariant evaluation."""

from app.advanced_reasoning.models import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolPlan,
    ToolPlanStep,
)
from app.advanced_reasoning.planner import AdvancedReasoningPlanner
from app.advanced_reasoning.tools import AdvancedToolRegistry, validate_and_order_plan
from app.core.chat_modes import ChatModeKey
from app.evaluation.models import AdvancedReasoningCase, EvaluationDataset, EvaluationSuiteResult
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.evaluation.suites.fakes import StaticTool
from app.llm.factory import create_llm_client
from app.routing.models import InternalRoute, RoutingSource, SupervisorDecision
from app.routing.registry import get_agent_registry

_ROUTES = {
    "sql": InternalRoute.SQL,
    "forecasting": InternalRoute.FORECASTING,
    "knowledge_catalog": InternalRoute.KNOWLEDGE_CATALOG,
    "data_discovery": InternalRoute.DATA_DISCOVERY,
    "data_quality": InternalRoute.DATA_QUALITY,
    "semantica": InternalRoute.SEMANTICA,
}


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    registry = AdvancedToolRegistry(
        (
            StaticTool(name, route, execute=_successful_execution(name))
            for name, route in _ROUTES.items()
        ),
        agent_registry=get_agent_registry(),
    )

    def one(raw_case):
        case = AdvancedReasoningCase.model_validate(raw_case)
        if context.profile.value == "live":
            result = AdvancedReasoningPlanner(
                create_llm_client(context.settings),
                registry,
                max_subtasks=case.maximum_tool_calls,
                max_tool_calls=case.maximum_tool_calls,
                max_replans=1,
            ).run(
                case.question,
                SupervisorDecision(
                    route=_ROUTES[case.expected_tool_names[0]],
                    confidence=1,
                    source=RoutingSource.LLM,
                    selected_mode=ChatModeKey.AUTO,
                    reason_code="evaluation_live",
                ),
            )
            selected = tuple(item.tool_name for item in result.tool_results)
            completed = all(
                item.status is ToolExecutionStatus.SUCCESS for item in result.tool_results
            )
        else:
            steps = tuple(
                ToolPlanStep(
                    step_id=f"step-{index}",
                    tool_name=name,
                    instruction=f"Evaluate the approved {name} request",
                    depends_on=() if index == 1 else (f"step-{index - 1}",),
                )
                for index, name in enumerate(case.tool_names, start=1)
            )
            ordered = validate_and_order_plan(ToolPlan(steps=steps), registry)
            selected = tuple(item.tool_name for item in ordered)
            completed = True
        invalid = sum(not registry.is_available(name) for name in selected)
        selection = float(set(case.expected_tool_names) <= set(selected))
        forbidden = len(set(selected) & set(case.forbidden_tools))
        budget = float(len(selected) > case.maximum_tool_calls)
        passed = bool(selection) and completed and not invalid and not forbidden and not budget
        return pass_fail(
            case,
            passed,
            metrics={
                "tool_selection": selection,
                "completed": float(completed),
                "budget_violation": budget,
                "invalid_tool": float(invalid + forbidden),
            },
            expected=", ".join(case.expected_tool_names),
            actual=", ".join(selected),
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "tool_selection_accuracy": mean_case_metric(items, "tool_selection"),
            "completion_rate": mean_case_metric(items, "completed"),
            "budget_violation_count": sum(i.metrics.get("budget_violation", 0) for i in items),
            "invalid_tool_count": sum(i.metrics.get("invalid_tool", 0) for i in items),
        },
    )


def _successful_execution(name: str):
    def execute(instruction: str) -> ToolExecutionResult:
        del instruction
        return ToolExecutionResult(
            step_id="pending",
            tool_name=name,
            status=ToolExecutionStatus.SUCCESS,
            summary="The approved evaluation tool completed with synthetic evidence.",
        )

    return execute
