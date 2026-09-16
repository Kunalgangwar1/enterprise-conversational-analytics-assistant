"""Unit tests for thin routing and specialist orchestration."""

from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.auth.authorization import AuthorizationService
from app.auth.models import AuthMethod, AuthPrincipal
from app.auth.roles import AppRole
from app.chat.exceptions import (
    ChatSQLGenerationError,
    InvalidChatStrategyError,
)
from app.chat.models import ChatRequest, SQLStrategy
from app.chat.orchestrator import ChatOrchestrator
from app.chat.specialist_registry import ChatSpecialistRegistry
from app.core.chat_modes import ChatModeKey, chat_mode_registry
from app.data_discovery.models import DataDiscoveryResult, DatasetMatch
from app.data_quality.models import DataQualityCitation, DataQualityResult
from app.forecasting.models import (
    ForecastChartMetadata,
    ForecastFrequency,
    ForecastMetrics,
    ForecastPoint,
    ForecastResult,
)
from app.knowledge_catalog.models import (
    KnowledgeCatalogResult,
    KnowledgeCitation,
    RetrievalMethod,
)
from app.nlp2sql.models import (
    NLP2SQLResult,
    SQLValidationDecision,
    SQLValidationResult,
)
from app.nlp2sql.multihop.models import (
    MultiHopBudgetSnapshot,
    MultiHopResult,
    MultiHopSynthesis,
)
from app.routing.models import InternalRoute, RoutingSource, SupervisorDecision
from app.sessions.models import SessionState
from app.sql_results.models import SummarySource


def _state(mode: ChatModeKey) -> SessionState:
    return SessionState(
        browser_session_id=str(uuid4()),
        tab_id="tab-test",
        selected_mode=mode,
    )


def _principal(role: AppRole = AppRole.ANALYST) -> AuthPrincipal:
    return AuthorizationService().enrich(
        AuthPrincipal(
            subject="test-user",
            roles=(role,),
            authentication_method=AuthMethod.DEVELOPMENT,
        )
    )


def _supervisor(route: InternalRoute) -> MagicMock:
    supervisor = MagicMock()
    supervisor.route.return_value = SupervisorDecision(
        route=route,
        confidence=1,
        source=RoutingSource.FORCED_MODE,
        selected_mode=ChatModeKey.AUTO,
    )
    return supervisor


def _registry(**providers: object) -> ChatSpecialistRegistry:
    return ChatSpecialistRegistry(
        **{name: (lambda value=value: value) for name, value in providers.items()}
    )


def _orchestrator(route: InternalRoute, **providers: object) -> tuple[ChatOrchestrator, MagicMock]:
    supervisor = _supervisor(route)
    return (
        ChatOrchestrator(supervisor, _registry(**providers), chat_mode_registry),
        supervisor,
    )


def _accepted_sql(decision: SQLValidationDecision = SQLValidationDecision.ACCEPT) -> NLP2SQLResult:
    sql = "SELECT COUNT(*) AS value FROM claims WHERE claim_external_id = 'T001'"
    return NLP2SQLResult(
        selected_domains=("claims",),
        selected_tables=("claims",),
        initial_sql=sql,
        generated_sql=sql,
        final_sql=sql if decision is SQLValidationDecision.ACCEPT else None,
        validation=SQLValidationResult(decision=decision, score=1, attempt=1),
        generation_attempt=1,
        rewrite_count=0,
        llm_call_count=4,
    )


def test_standard_sql_is_validated_but_not_executed_and_keeps_safe_tokens() -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql()
    orchestrator, supervisor = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)

    turn = orchestrator.run(
        ChatRequest(message="Count claim C0000001", sql_strategy=SQLStrategy.STANDARD),
        _state(ChatModeKey.SQL),
        _principal(),
    )

    assert turn.response.response_type == "sql"
    assert turn.accepted_sql is not None and "T001" in turn.accepted_sql
    assert "C0000001" not in turn.response.payload.sql
    assert turn.token_mappings[0].original_value == "C0000001"
    assert nlp2sql.generate_sql.call_args.args[0].endswith("T001")
    supervisor.route.assert_called_once()


def test_rejected_standard_sql_is_not_returned_for_execution() -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql(SQLValidationDecision.REJECT)
    orchestrator, _ = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)
    with pytest.raises(ChatSQLGenerationError):
        orchestrator.run(
            ChatRequest(message="Count claims", sql_strategy=SQLStrategy.STANDARD),
            _state(ChatModeKey.SQL),
            _principal(),
        )


def test_custom_context_is_privacy_processed_as_current_turn_data() -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql()
    orchestrator, _ = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)
    turn = orchestrator.run(
        ChatRequest(
            message="Count claims",
            sql_strategy=SQLStrategy.STANDARD,
            custom_context="Only claim C0000001 for analyst@example.test",
        ),
        _state(ChatModeKey.SQL),
        _principal(),
    )
    safe_question = nlp2sql.generate_sql.call_args.args[0]
    assert "C0000001" not in safe_question
    assert "analyst@example.test" not in safe_question
    assert "T001" in safe_question
    assert turn.token_mappings


def test_raw_input_is_privacy_processed_before_supervisor_routing() -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql()
    orchestrator, supervisor = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)

    orchestrator.run(
        ChatRequest(message="Count claim C0000001"),
        _state(ChatModeKey.AUTO),
        _principal(),
    )

    supervisor.route.assert_called_once_with("Count claim T001", ChatModeKey.AUTO)


def test_advanced_strategy_reuses_multihop_agent() -> None:
    agent = MagicMock()
    agent.run.return_value = MultiHopResult(
        answer_markdown="Advanced answer",
        synthesis=MultiHopSynthesis(summary="Advanced answer"),
        hops=(),
        budget=MultiHopBudgetSnapshot(
            hops_planned=1,
            hops_executed=1,
            rows_per_hop=(1,),
            total_rows_returned=1,
            elapsed_seconds=0.1,
        ),
    )
    orchestrator, _ = _orchestrator(InternalRoute.SQL, multihop=agent)
    turn = orchestrator.run(
        ChatRequest(message="Compare claim groups", sql_strategy=SQLStrategy.ADVANCED),
        _state(ChatModeKey.SQL),
        _principal(),
    )
    assert turn.response.response_type == "advanced"
    agent.run.assert_called_once()


def test_forecasting_strategy_reuses_forecasting_agent() -> None:
    agent = MagicMock()
    agent.forecast.return_value = ForecastResult(
        metric_label="Monthly claims",
        frequency=ForecastFrequency.MONTH,
        horizon_periods=1,
        selected_model="naive",
        backtest_metrics=ForecastMetrics(mae=1, rmse=2, smape=3),
        historical_points=(),
        forecast_points=(
            ForecastPoint(period=date(2026, 1, 1), predicted=10, lower_bound=6, upper_bound=14),
        ),
        summary="Approximate aggregate forecast.",
        summary_source=SummarySource.LLM,
        chart=ForecastChartMetadata(title="Monthly claims"),
        warnings=("Approximate interval.",),
    )
    orchestrator, _ = _orchestrator(InternalRoute.SQL, forecasting=agent)
    turn = orchestrator.run(
        ChatRequest(message="Forecast monthly claims", sql_strategy=SQLStrategy.FORECASTING),
        _state(ChatModeKey.SQL),
        _principal(),
    )
    assert turn.response.response_type == "forecast"
    assert turn.response.payload.selected_model == "naive"
    agent.forecast.assert_called_once()


@pytest.mark.parametrize(
    ("mode", "route", "provider_name", "result", "response_type"),
    [
        (
            ChatModeKey.DATA_DISCOVERY,
            InternalRoute.DATA_DISCOVERY,
            "data_discovery",
            DataDiscoveryResult(
                matches=(
                    DatasetMatch(
                        dataset="claims",
                        repository="synthetic-health",
                        table="claims",
                        domain="claims",
                        description="Synthetic claims",
                        matched_fields=("dataset",),
                        score=1,
                    ),
                )
            ),
            "data_discovery",
        ),
        (
            ChatModeKey.KNOWLEDGE_CATALOG,
            InternalRoute.KNOWLEDGE_CATALOG,
            "knowledge_catalog",
            KnowledgeCatalogResult(
                answer="Catalog answer",
                retrieval_method=RetrievalMethod.HIERARCHICAL,
                citations=(
                    KnowledgeCitation(
                        id="c1", title="Claims", section="Meaning", source_path="claims.md"
                    ),
                ),
            ),
            "knowledge_catalog",
        ),
        (
            ChatModeKey.DATA_QUALITY,
            InternalRoute.DATA_QUALITY,
            "data_quality",
            DataQualityResult(
                answer="Quality answer",
                citations=(
                    DataQualityCitation(
                        id="d1", title="Claims", topic="freshness", source_path="claims.md"
                    ),
                ),
            ),
            "data_quality",
        ),
        (
            ChatModeKey.SEMANTICA,
            InternalRoute.SEMANTICA,
            "semantica",
            KnowledgeCatalogResult(
                answer="Semantic answer",
                retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
                citations=(),
            ),
            "semantica",
        ),
    ],
)
def test_explicit_specialist_modes_reuse_existing_agents(
    mode: ChatModeKey,
    route: InternalRoute,
    provider_name: str,
    result: object,
    response_type: str,
) -> None:
    specialist = MagicMock()
    if provider_name == "data_discovery":
        specialist.search.return_value = result
    else:
        specialist.answer.return_value = result
    orchestrator, supervisor = _orchestrator(route, **{provider_name: specialist})
    turn = orchestrator.run(ChatRequest(message="Safe question"), _state(mode), _principal())
    assert turn.response.response_type == response_type
    supervisor.route.assert_called_once_with("Safe question", mode)


@pytest.mark.parametrize("route", [InternalRoute.CHAT, InternalRoute.HELP])
def test_chat_and_help_routes_are_deterministic(route: InternalRoute) -> None:
    orchestrator, _ = _orchestrator(route)
    turn = orchestrator.run(
        ChatRequest(message="hello"),
        _state(ChatModeKey.AUTO),
        _principal(),
    )
    assert turn.response.response_type == "message"
    assert turn.response.content


def test_group_access_returns_only_current_principal_access() -> None:
    orchestrator, _ = _orchestrator(InternalRoute.GROUP_ACCESS)
    turn = orchestrator.run(
        ChatRequest(message="What can I access?"),
        _state(ChatModeKey.GROUP_ACCESS),
        _principal(AppRole.VIEWER),
    )
    assert turn.response.response_type == "group_access"
    assert "sql.generate" not in turn.response.content


def test_sql_strategy_is_rejected_outside_data_intelligence() -> None:
    orchestrator, _ = _orchestrator(InternalRoute.DATA_DISCOVERY)
    with pytest.raises(InvalidChatStrategyError):
        orchestrator.run(
            ChatRequest(message="Find claims", sql_strategy=SQLStrategy.STANDARD),
            _state(ChatModeKey.DATA_DISCOVERY),
            _principal(),
        )
