"""Explicit application-tool registry and adapters for the generic planner."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.advanced_reasoning.exceptions import (
    AdvancedReasoningPlanError,
    AdvancedToolUnavailableError,
)
from app.advanced_reasoning.models import (
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolPlan,
    ToolPlanStep,
)
from app.advanced_reasoning.security import contains_disallowed_executable_content
from app.auth.permissions import Permission
from app.core.feature_flags import ToolFeatureFlags
from app.data_discovery.search import DataDiscoveryService
from app.data_quality.agent import DataQualityAgent
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.models import SQLValidationDecision
from app.privacy.models import TokenMappingEntry
from app.routing.models import InternalRoute
from app.routing.registry import AgentRegistry
from app.semantica.agent import SemanticaAgent
from app.sql_results.service import SQLExecutionService

if TYPE_CHECKING:
    from app.forecasting.agent import ForecastingAgent


@runtime_checkable
class AdvancedTool(Protocol):
    name: str
    route: InternalRoute
    description: str

    def execute(self, instruction: str) -> ToolExecutionResult:
        """Run one safe application-level operation."""
        ...


class AdvancedToolRegistry:
    """Expose only injected, enabled application adapters by stable names."""

    def __init__(
        self,
        tools: Iterable[AdvancedTool],
        *,
        agent_registry: AgentRegistry,
        enabled_tool_names: Iterable[str] | None = None,
    ) -> None:
        tool_items = tuple(tools)
        by_name = {tool.name: tool for tool in tool_items}
        if len(by_name) != len(tool_items):
            raise ValueError("Advanced tool names must be unique")
        self._tools = by_name
        self._agent_registry = agent_registry
        self._enabled_names = (
            frozenset(by_name) if enabled_tool_names is None else frozenset(enabled_tool_names)
        )

    def authorized(self, permissions: frozenset[Permission]) -> AdvancedToolRegistry:
        """Return a request-scoped registry with unauthorized tools removed up front."""

        authorized_names = {
            name
            for name in self._enabled_names
            if _TOOL_PERMISSIONS.get(name, frozenset()) <= permissions
        }
        return AdvancedToolRegistry(
            self._tools.values(),
            agent_registry=self._agent_registry,
            enabled_tool_names=authorized_names,
        )

    def available_names(self) -> tuple[str, ...]:
        """Return stable authorized names for tests and planner composition."""

        return tuple(name for name in sorted(self._tools) if self.is_available(name))

    def is_available(self, tool_name: str) -> bool:
        tool = self._tools.get(tool_name)
        return bool(
            tool is not None
            and tool_name in self._enabled_names
            and self._agent_registry.is_enabled(tool.route)
        )

    def has_route(self, route: InternalRoute) -> bool:
        return any(
            tool.route is route and self.is_available(tool.name) for tool in self._tools.values()
        )

    def descriptions(self) -> tuple[str, ...]:
        return tuple(
            f"{name}: {self._tools[name].description}"
            for name in sorted(self._tools)
            if self.is_available(name)
        )

    def require(self, tool_name: str) -> AdvancedTool:
        if not self.is_available(tool_name):
            raise AdvancedToolUnavailableError(
                f"Advanced plan references unavailable tool '{tool_name}'"
            )
        return self._tools[tool_name]

    def execute(self, step: ToolPlanStep) -> ToolExecutionResult:
        tool = self.require(step.tool_name)
        try:
            result = tool.execute(step.instruction)
        except Exception:
            return ToolExecutionResult(
                step_id=step.step_id,
                tool_name=step.tool_name,
                status=ToolExecutionStatus.FAILED,
                summary="The approved application tool could not complete this step.",
                warning="Tool execution failed without exposing internal details.",
            )
        return result.model_copy(update={"step_id": step.step_id, "tool_name": step.tool_name})


def enabled_advanced_tool_names(flags: ToolFeatureFlags) -> frozenset[str]:
    """Map existing tool rollout flags without exposing unimplemented routes."""

    candidates = {
        "sql",
        "forecasting",
        "knowledge_catalog",
        "data_discovery",
        "data_quality",
        "semantica",
    }
    return frozenset(name for name in candidates if getattr(flags, name))


def validate_and_order_plan(
    plan: ToolPlan,
    registry: AdvancedToolRegistry,
    *,
    completed_step_ids: Sequence[str] = (),
) -> tuple[ToolPlanStep, ...]:
    """Validate tool/dependency policy and return a stable topological order."""

    steps_by_id = {step.step_id: step for step in plan.steps}
    if len(steps_by_id) != len(plan.steps):
        raise AdvancedReasoningPlanError("Advanced tool-plan step IDs must be unique")
    completed = set(completed_step_ids)
    if set(steps_by_id) & completed:
        raise AdvancedReasoningPlanError("Advanced replan cannot reuse a completed step ID")
    for step in plan.steps:
        registry.require(step.tool_name)
        if contains_disallowed_executable_content(step.instruction):
            raise AdvancedReasoningPlanError(
                "Advanced tool instructions cannot contain executable code, SQL, or URLs"
            )
        if step.step_id in step.depends_on:
            raise AdvancedReasoningPlanError("Advanced tool plan cannot contain self-dependencies")
        unknown = set(step.depends_on) - set(steps_by_id) - completed
        if unknown:
            raise AdvancedReasoningPlanError("Advanced tool plan contains an unknown dependency")

    pending = list(plan.steps)
    ordered: list[ToolPlanStep] = []
    resolved = set(completed)
    while pending:
        ready = [step for step in pending if set(step.depends_on) <= resolved]
        if not ready:
            raise AdvancedReasoningPlanError("Advanced tool plan dependency graph contains a cycle")
        for step in ready:
            pending.remove(step)
            ordered.append(step)
            resolved.add(step.step_id)
    return tuple(ordered)


class SQLAnalyticsTool:
    name = "sql"
    route = InternalRoute.SQL
    description = "Generate, validate, and execute one bounded read-only analytical SQL request."

    def __init__(
        self,
        nlp2sql_agent: NLP2SQLAgent,
        execution_service: SQLExecutionService,
        token_mappings: Sequence[TokenMappingEntry] = (),
    ) -> None:
        self._nlp2sql_agent = nlp2sql_agent
        self._execution_service = execution_service
        self._token_mappings = tuple(token_mappings)

    def execute(self, instruction: str) -> ToolExecutionResult:
        generated = self._nlp2sql_agent.generate_sql(instruction)
        if generated.validation.decision is not SQLValidationDecision.ACCEPT:
            raise AdvancedReasoningPlanError("SQL subtask was not accepted by validation")
        result = self._execution_service.execute(
            final_sql=generated.final_sql,
            decision=generated.validation.decision,
            token_mappings=self._token_mappings,
            safe_question=instruction,
        )
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=result.summary,
            structured_payload={
                "columns": result.columns,
                "row_count": result.row_count,
                "truncated": result.truncated,
            },
        )


class ForecastingTool:
    name = "forecasting"
    route = InternalRoute.FORECASTING
    description = "Forecast an aggregate operational metric from validated historical SQL data."

    def __init__(
        self,
        agent: ForecastingAgent,
        token_mappings: Sequence[TokenMappingEntry] = (),
    ) -> None:
        self._agent = agent
        self._token_mappings = tuple(token_mappings)

    def execute(self, instruction: str) -> ToolExecutionResult:
        result = self._agent.forecast(instruction, self._token_mappings)
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=result.summary,
            structured_payload={
                "metric_label": result.metric_label,
                "frequency": result.frequency.value,
                "horizon_periods": result.horizon_periods,
                "selected_model": result.selected_model,
                "backtest_metrics": result.backtest_metrics.model_dump(mode="json"),
                "forecast_points": [
                    point.model_dump(mode="json") for point in result.forecast_points
                ],
            },
            warning=" ".join(result.warnings),
        )


class KnowledgeCatalogTool:
    name = "knowledge_catalog"
    route = InternalRoute.KNOWLEDGE_CATALOG
    description = "Answer catalog, lineage, policy, and governed data meaning questions."

    def __init__(self, agent: KnowledgeCatalogAgent) -> None:
        self._agent = agent

    def execute(self, instruction: str) -> ToolExecutionResult:
        result = self._agent.answer(instruction)
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=result.answer,
            citations=tuple(item.id for item in result.citations),
        )


class DataDiscoveryTool:
    name = "data_discovery"
    route = InternalRoute.DATA_DISCOVERY
    description = "Find registered datasets, tables, domains, and repositories deterministically."

    def __init__(self, service: DataDiscoveryService) -> None:
        self._service = service

    def execute(self, instruction: str) -> ToolExecutionResult:
        result = self._service.search(instruction)
        summary = (
            "; ".join(
                f"{item.dataset} ({item.table}, {item.repository})" for item in result.matches
            )
            or "No registered dataset matched the request."
        )
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=summary,
            structured_payload={"match_count": len(result.matches)},
        )


class DataQualityTool:
    name = "data_quality"
    route = InternalRoute.DATA_QUALITY
    description = "Answer from documented synthetic data-quality rules and remediation guidance."

    def __init__(self, agent: DataQualityAgent) -> None:
        self._agent = agent

    def execute(self, instruction: str) -> ToolExecutionResult:
        result = self._agent.answer(instruction)
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=result.answer,
            citations=tuple(item.id for item in result.citations),
        )


class SemanticaTool:
    name = "semantica"
    route = InternalRoute.SEMANTICA
    description = "Answer from graph-expanded Semantica catalog evidence."

    def __init__(self, agent: SemanticaAgent) -> None:
        self._agent = agent

    def execute(self, instruction: str) -> ToolExecutionResult:
        result = self._agent.answer(instruction)
        return ToolExecutionResult(
            step_id="pending",
            tool_name=self.name,
            status=ToolExecutionStatus.SUCCESS,
            summary=result.answer,
            citations=tuple(item.id for item in result.citations),
        )


_TOOL_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "sql": frozenset({Permission.SQL_GENERATE, Permission.SQL_EXECUTE, Permission.SQL_ADVANCED}),
    "forecasting": frozenset({Permission.FORECAST_RUN}),
    "knowledge_catalog": frozenset({Permission.KNOWLEDGE_CATALOG_READ}),
    "data_discovery": frozenset({Permission.DATA_DISCOVERY_READ}),
    "data_quality": frozenset({Permission.DATA_QUALITY_READ}),
    "semantica": frozenset({Permission.SEMANTICA_READ}),
}
