"""Route/strategy authorization tests for chat orchestration."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.exceptions import PermissionDeniedError
from app.auth.roles import AppRole
from app.chat.models import ChatRequest, SQLStrategy
from app.chat.orchestrator import ChatOrchestrator
from app.chat.specialist_registry import ChatSpecialistRegistry
from app.core.chat_modes import ChatModeKey, chat_mode_registry
from app.core.config import Settings
from app.forecasting.models import (
    ForecastChartMetadata,
    ForecastFrequency,
    ForecastMetrics,
    ForecastPoint,
    ForecastResult,
)
from app.knowledge_catalog.models import KnowledgeCatalogResult, RetrievalMethod
from app.main import create_app
from app.nlp2sql.models import NLP2SQLResult, SQLValidationDecision, SQLValidationResult
from app.nlp2sql.multihop.models import (
    MultiHopBudgetSnapshot,
    MultiHopResult,
    MultiHopSynthesis,
)
from app.routing.models import InternalRoute, RoutingSource, SupervisorDecision
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import SessionState
from app.sql_results.models import SummarySource
from tests.auth.helpers import FixedAuthenticationBackend, principal


def _state(mode: ChatModeKey) -> SessionState:
    return SessionState(
        browser_session_id=str(uuid4()),
        tab_id="auth-tab",
        owner_subject="synthetic-user",
        selected_mode=mode,
    )


def _orchestrator(route: InternalRoute, **providers: object):
    supervisor = MagicMock()
    supervisor.route.return_value = SupervisorDecision(
        route=route,
        confidence=1,
        source=RoutingSource.FORCED_MODE,
        selected_mode=ChatModeKey.AUTO,
    )
    registry = ChatSpecialistRegistry(
        **{name: (lambda value=value: value) for name, value in providers.items()}
    )
    return ChatOrchestrator(supervisor, registry, chat_mode_registry), supervisor


def _accepted_sql() -> NLP2SQLResult:
    sql = "SELECT COUNT(*) AS value FROM claims"
    return NLP2SQLResult(
        selected_domains=("claims",),
        selected_tables=("claims",),
        initial_sql=sql,
        generated_sql=sql,
        final_sql=sql,
        validation=SQLValidationResult(
            decision=SQLValidationDecision.ACCEPT,
            score=1,
            attempt=1,
        ),
        generation_attempt=1,
        rewrite_count=0,
        llm_call_count=4,
    )


def test_viewer_can_use_catalog_without_identity_metadata_entering_prompt() -> None:
    catalog = MagicMock()
    catalog.answer.return_value = KnowledgeCatalogResult(
        answer="Synthetic catalog answer",
        retrieval_method=RetrievalMethod.HIERARCHICAL,
    )
    orchestrator, supervisor = _orchestrator(
        InternalRoute.KNOWLEDGE_CATALOG,
        knowledge_catalog=catalog,
    )

    result = orchestrator.run(
        ChatRequest(message="Explain the claims dataset"),
        _state(ChatModeKey.KNOWLEDGE_CATALOG),
        principal(AppRole.VIEWER),
    )

    assert result.response.response_type == "knowledge_catalog"
    routed_question = supervisor.route.call_args.args[0]
    assert "synthetic-user" not in routed_question
    assert "example.invalid" not in routed_question
    assert "viewer" not in routed_question


@pytest.mark.parametrize(
    ("mode", "strategy"),
    [
        (ChatModeKey.SQL, SQLStrategy.STANDARD),
        (ChatModeKey.SQL, SQLStrategy.ADVANCED),
        (ChatModeKey.SQL, SQLStrategy.FORECASTING),
    ],
)
def test_viewer_cannot_use_privileged_sql_strategies(
    mode: ChatModeKey,
    strategy: SQLStrategy,
) -> None:
    nlp2sql = MagicMock()
    orchestrator, _ = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)
    with pytest.raises(PermissionDeniedError):
        orchestrator.run(
            ChatRequest(message="Analyze claims", sql_strategy=strategy),
            _state(mode),
            principal(AppRole.VIEWER),
        )
    nlp2sql.generate_sql.assert_not_called()


def test_viewer_auto_route_to_sql_is_forbidden() -> None:
    nlp2sql = MagicMock()
    orchestrator, _ = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)
    with pytest.raises(PermissionDeniedError):
        orchestrator.run(
            ChatRequest(message="Count claims"),
            _state(ChatModeKey.AUTO),
            principal(AppRole.VIEWER),
        )
    nlp2sql.generate_sql.assert_not_called()


@pytest.mark.parametrize("explicit_mode", [False, True], ids=["auto", "explicit-sql"])
def test_chat_api_returns_403_before_viewer_sql_execution(
    tmp_path: Path,
    explicit_mode: bool,
) -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql()
    orchestrator, _ = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)
    application = create_app(
        Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path),
        session_store=JsonFileSessionStore(tmp_path / "sessions"),
        chat_orchestrator=orchestrator,
        authentication_backend=FixedAuthenticationBackend(principal(AppRole.VIEWER)),
    )
    with TestClient(application) as client:
        if explicit_mode:
            selected = client.post(
                "/chat/select-mode",
                json={"mode": "sql"},
                headers={"X-Tab-Id": "viewer-tab"},
            )
            assert selected.status_code == 200
        response = client.post(
            "/chat",
            json={
                "message": "Count claims",
                **({"sql_strategy": "standard"} if explicit_mode else {}),
            },
            headers={"X-Tab-Id": "viewer-tab"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    nlp2sql.generate_sql.assert_not_called()


def test_analyst_can_generate_standard_sql() -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql()
    orchestrator, _ = _orchestrator(InternalRoute.SQL, nlp2sql=nlp2sql)
    result = orchestrator.run(
        ChatRequest(message="Count claims", sql_strategy=SQLStrategy.STANDARD),
        _state(ChatModeKey.SQL),
        principal(AppRole.ANALYST),
    )
    assert result.accepted_sql == "SELECT COUNT(*) AS value FROM claims"


def test_analyst_can_use_advanced_and_forecasting() -> None:
    multihop = MagicMock()
    multihop.run.return_value = MultiHopResult(
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
    forecasting = MagicMock()
    forecasting.forecast.return_value = ForecastResult(
        metric_label="Monthly claims",
        frequency=ForecastFrequency.MONTH,
        horizon_periods=1,
        selected_model="naive",
        backtest_metrics=ForecastMetrics(mae=1, rmse=1, smape=1),
        historical_points=(),
        forecast_points=(
            ForecastPoint(
                period=date(2026, 1, 1),
                predicted=2,
                lower_bound=1,
                upper_bound=3,
            ),
        ),
        summary="Synthetic forecast",
        summary_source=SummarySource.DETERMINISTIC,
        chart=ForecastChartMetadata(title="Synthetic forecast"),
    )
    orchestrator, _ = _orchestrator(
        InternalRoute.SQL,
        multihop=multihop,
        forecasting=forecasting,
    )
    analyst = principal(AppRole.ANALYST)

    advanced = orchestrator.run(
        ChatRequest(message="Compare cohorts", sql_strategy=SQLStrategy.ADVANCED),
        _state(ChatModeKey.SQL),
        analyst,
    )
    forecast = orchestrator.run(
        ChatRequest(message="Forecast claims", sql_strategy=SQLStrategy.FORECASTING),
        _state(ChatModeKey.SQL),
        analyst,
    )
    assert advanced.response.response_type == "advanced"
    assert forecast.response.response_type == "forecast"


def test_group_access_is_deterministic_self_introspection() -> None:
    orchestrator, _ = _orchestrator(InternalRoute.GROUP_ACCESS)
    viewer = principal(AppRole.VIEWER)
    result = orchestrator.run(
        ChatRequest(message="What permissions do I have?"),
        _state(ChatModeKey.GROUP_ACCESS),
        viewer,
    )
    assert result.response.response_type == "group_access"
    assert result.response.payload.roles == (AppRole.VIEWER,)
    assert all("sql." not in item.value for item in result.response.payload.effective_permissions)

    with pytest.raises(PermissionDeniedError):
        orchestrator.run(
            ChatRequest(message="What can another-user@example.invalid access?"),
            _state(ChatModeKey.GROUP_ACCESS),
            viewer,
        )
