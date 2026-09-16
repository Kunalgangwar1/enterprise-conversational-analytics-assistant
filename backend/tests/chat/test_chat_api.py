"""API and session tests for unified chat and SQL generation/execution continuity."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.chat.orchestrator import ChatOrchestrator
from app.chat.specialist_registry import ChatSpecialistRegistry
from app.core.chat_modes import ChatModeKey, chat_mode_registry
from app.core.config import Settings
from app.data_discovery.models import DataDiscoveryResult, DatasetMatch
from app.main import create_app
from app.nlp2sql.models import (
    NLP2SQLResult,
    SQLValidationDecision,
    SQLValidationResult,
)
from app.routing.exceptions import RoutingProviderError
from app.routing.models import InternalRoute, RoutingSource, SupervisorDecision
from app.sessions.identity import SessionIdentity
from app.sessions.json_store import JsonFileSessionStore
from app.sql_results.models import (
    ChartMetadata,
    ChartType,
    SQLAnalyticsResult,
    SummarySource,
)
from app.sql_results.service import SQLExecutionService


def _decision(route: InternalRoute) -> SupervisorDecision:
    return SupervisorDecision(
        route=route,
        confidence=1,
        source=RoutingSource.FORCED_MODE,
        selected_mode=ChatModeKey.AUTO,
    )


def _accepted_sql() -> NLP2SQLResult:
    sql = "SELECT COUNT(*) AS value FROM claims WHERE claim_external_id = 'T001'"
    return NLP2SQLResult(
        selected_domains=("claims",),
        selected_tables=("claims",),
        initial_sql=sql,
        generated_sql=sql,
        final_sql=sql,
        validation=SQLValidationResult(decision=SQLValidationDecision.ACCEPT, score=1, attempt=1),
        generation_attempt=1,
        rewrite_count=0,
        llm_call_count=4,
    )


def _analytics_result() -> SQLAnalyticsResult:
    return SQLAnalyticsResult(
        columns=["value"],
        rows=[{"value": Decimal("4")}],
        row_count=1,
        truncated=False,
        execution_elapsed_ms=1,
        summary="Four synthetic claims matched.",
        summary_source=SummarySource.DETERMINISTIC,
        chart=ChartMetadata(
            chart_type=ChartType.TABLE,
            title="Claims",
            selection_rule="single_value",
        ),
    )


def _app(
    tmp_path: Path,
    *,
    route: InternalRoute,
    providers: dict[str, object],
) -> tuple[TestClient, JsonFileSessionStore, MagicMock]:
    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)
    store = JsonFileSessionStore(tmp_path / "sessions")
    supervisor = MagicMock()
    supervisor.route.return_value = _decision(route)
    registry = ChatSpecialistRegistry(
        **{name: (lambda value=value: value) for name, value in providers.items()}
    )
    orchestrator = ChatOrchestrator(supervisor, registry, chat_mode_registry)
    execution = MagicMock(spec=SQLExecutionService)
    execution.execute.return_value = _analytics_result()
    application = create_app(
        settings,
        session_store=store,
        sql_execution_service=execution,
        chat_orchestrator=orchestrator,
    )
    return TestClient(application), store, execution


def _identity(client: TestClient, settings: Settings, tab_id: str) -> SessionIdentity:
    return SessionIdentity(
        browser_session_id=client.cookies.get(settings.session_cookie_name),
        tab_id=tab_id,
    )


def test_post_chat_validates_empty_message() -> None:
    application = create_app(Settings(_env_file=None, app_env="test"))
    with TestClient(application) as client:
        response = client.post("/chat", json={"message": "   "}, headers={"X-Tab-Id": "tab-a"})
    assert response.status_code == 422


def test_select_sql_chat_then_execute_uses_server_owned_sql_and_current_mapping(
    tmp_path: Path,
) -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = _accepted_sql()
    client, store, execution = _app(
        tmp_path, route=InternalRoute.SQL, providers={"nlp2sql": nlp2sql}
    )
    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)
    with client:
        selected = client.post(
            "/chat/select-mode",
            json={"mode": "sql"},
            headers={"X-Tab-Id": "tab-a"},
        )
        generated = client.post(
            "/chat",
            json={"message": "Count claim C0000001", "sql_strategy": "standard"},
            headers={"X-Tab-Id": "tab-a"},
        )
        executed = client.post(
            "/chat/execute-sql",
            json={"sql": "DELETE FROM claims"},
            headers={"X-Tab-Id": "tab-a"},
        )

        assert selected.status_code == generated.status_code == executed.status_code == 200
        generated_body = generated.json()
        assert generated_body["response_type"] == "sql"
        assert "T001" in generated_body["payload"]["sql"]
        assert "C0000001" not in generated.text
        assert "token_mapping" not in generated.text
        state = store.load(_identity(client, settings, "tab-a"))

    assert state is not None
    assert state.selected_mode is ChatModeKey.SQL
    assert state.last_generated_sql == _accepted_sql().final_sql
    assert state.last_token_mapping == {"T001": "C0000001"}
    assert [message.content for message in state.chat_history] == [
        "Count claim C0000001",
        "SQL was generated and validated. Review it before running the query.",
    ]
    assert executed.json()["rows"] == [{"value": "4"}]
    call = execution.execute.call_args
    assert call.kwargs["final_sql"] == _accepted_sql().final_sql
    assert call.kwargs["token_mappings"][0].original_value == "C0000001"


def test_custom_context_is_not_persisted_and_session_has_no_mapping_history(
    tmp_path: Path,
) -> None:
    discovery = MagicMock()
    discovery.search.return_value = DataDiscoveryResult()
    client, store, _ = _app(
        tmp_path,
        route=InternalRoute.DATA_DISCOVERY,
        providers={"data_discovery": discovery},
    )
    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)
    with client:
        client.post(
            "/chat/select-mode",
            json={"mode": "data_discovery"},
            headers={"X-Tab-Id": "tab-a"},
        )
        response = client.post(
            "/chat",
            json={"message": "Find claims", "custom_context": "temporary private context"},
            headers={"X-Tab-Id": "tab-a"},
        )
        state = store.load(_identity(client, settings, "tab-a"))

    assert response.status_code == 200
    assert state is not None
    serialized = state.model_dump_json()
    assert "temporary private context" not in serialized
    assert "custom_context" not in serialized
    assert "token_mapping_history" not in serialized


def test_data_discovery_chat_is_credential_free_and_structured(tmp_path: Path) -> None:
    discovery = MagicMock()
    discovery.search.return_value = DataDiscoveryResult(
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
    )
    client, _, _ = _app(
        tmp_path,
        route=InternalRoute.DATA_DISCOVERY,
        providers={"data_discovery": discovery},
    )
    with client:
        client.post(
            "/chat/select-mode",
            json={"mode": "data_discovery"},
            headers={"X-Tab-Id": "tab-a"},
        )
        response = client.post(
            "/chat", json={"message": "Find claims"}, headers={"X-Tab-Id": "tab-a"}
        )
    assert response.status_code == 200
    assert response.json()["payload"]["matches"][0]["dataset"] == "claims"


def test_tab_ids_keep_modes_and_history_isolated(tmp_path: Path) -> None:
    discovery = MagicMock()
    discovery.search.return_value = DataDiscoveryResult()
    client, store, _ = _app(
        tmp_path,
        route=InternalRoute.DATA_DISCOVERY,
        providers={"data_discovery": discovery},
    )
    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)
    with client:
        client.post(
            "/chat/select-mode",
            json={"mode": "data_discovery"},
            headers={"X-Tab-Id": "tab-a"},
        )
        client.post("/chat", json={"message": "Find claims"}, headers={"X-Tab-Id": "tab-a"})
        client.post(
            "/chat/select-mode",
            json={"mode": "knowledge_catalog"},
            headers={"X-Tab-Id": "tab-b"},
        )
        state_a = store.load(_identity(client, settings, "tab-a"))
        state_b = store.load(_identity(client, settings, "tab-b"))
    assert state_a is not None and state_b is not None
    assert state_a.selected_mode is ChatModeKey.DATA_DISCOVERY
    assert len(state_a.chat_history) == 2
    assert state_b.selected_mode is ChatModeKey.KNOWLEDGE_CATALOG
    assert state_b.chat_history == []


def test_group_access_and_provider_failures_use_safe_error_envelopes(tmp_path: Path) -> None:
    group_client, _, _ = _app(tmp_path / "group", route=InternalRoute.GROUP_ACCESS, providers={})
    with group_client:
        group_client.post(
            "/chat/select-mode",
            json={"mode": "group_access"},
            headers={"X-Tab-Id": "tab-a"},
        )
        unavailable = group_client.post(
            "/chat", json={"message": "Request access"}, headers={"X-Tab-Id": "tab-a"}
        )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "specialist_unavailable"

    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path / "provider")
    store = JsonFileSessionStore(tmp_path / "provider" / "sessions")
    supervisor = MagicMock()
    supervisor.route.side_effect = RoutingProviderError("secret provider details")
    orchestrator = ChatOrchestrator(supervisor, ChatSpecialistRegistry(), chat_mode_registry)
    app = create_app(settings, session_store=store, chat_orchestrator=orchestrator)
    with TestClient(app) as client:
        failed = client.post(
            "/chat", json={"message": "Analyze data"}, headers={"X-Tab-Id": "tab-a"}
        )
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "provider_unavailable"
    assert "secret" not in failed.text
