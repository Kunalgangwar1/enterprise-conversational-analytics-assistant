"""API tests for server-owned, tab-isolated accepted SQL execution."""

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.db.query.exceptions import (
    QueryDependencyUnavailableError,
    QueryExecutionError,
    QueryTimeoutError,
)
from app.main import create_app
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import SessionState
from app.sql_results import (
    ChartMetadata,
    ChartType,
    SQLAnalyticsResult,
    SQLExecutionService,
    SQLTokenResolutionError,
    SummarySource,
)


@dataclass(frozen=True)
class SQLExecutionAPIContext:
    client: TestClient
    store: JsonFileSessionStore
    service: MagicMock
    settings: Settings


@pytest.fixture
def sql_execution_api(tmp_path: Path) -> Iterator[SQLExecutionAPIContext]:
    settings = Settings(
        _env_file=None,
        app_name="Test Analytics API",
        app_env="test",
        artifacts_output_dir=tmp_path,
    )
    store = JsonFileSessionStore(tmp_path / "sessions")
    service = MagicMock(spec=SQLExecutionService)
    service.execute.return_value = _analytics_result()
    application = create_app(
        settings,
        session_store=store,
        sql_execution_service=service,
    )
    with TestClient(application) as client:
        yield SQLExecutionAPIContext(client, store, service, settings)


def _analytics_result() -> SQLAnalyticsResult:
    return SQLAnalyticsResult(
        columns=["specialty", "total_paid"],
        rows=[{"specialty": "Cardiology", "total_paid": Decimal("123.45")}],
        row_count=1,
        truncated=False,
        execution_elapsed_ms=2.5,
        summary="Cardiology has returned paid claims.",
        summary_source=SummarySource.DETERMINISTIC_FALLBACK,
        chart=ChartMetadata(
            chart_type=ChartType.BAR,
            x_axis="specialty",
            y_axes=("total_paid",),
            title="Total Paid by Specialty",
            selection_rule="categorical_numeric",
        ),
    )


def _seed_session(
    context: SQLExecutionAPIContext,
    *,
    browser_id: str,
    tab_id: str,
    sql: str | None,
    mapping: dict[str, str] | None = None,
) -> None:
    context.store.save(
        SessionState(
            browser_session_id=browser_id,
            tab_id=tab_id,
            owner_subject="dev-user",
            last_generated_sql=sql,
            last_token_mapping=mapping,
        )
    )


def _set_browser_cookie(context: SQLExecutionAPIContext, browser_id: str) -> None:
    context.client.cookies.set(context.settings.session_cookie_name, browser_id)


def test_execute_sql_exists_and_without_session_sql_returns_controlled_409(
    sql_execution_api: SQLExecutionAPIContext,
) -> None:
    response = sql_execution_api.client.post(
        "/chat/execute-sql",
        headers={"X-Tab-Id": "tab-a"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "no_validated_sql",
            "message": "No validated SQL is available for the current conversation.",
        }
    }
    sql_execution_api.service.execute.assert_not_called()


def test_endpoint_schema_has_no_client_sql_request_body(
    sql_execution_api: SQLExecutionAPIContext,
) -> None:
    operation = sql_execution_api.client.get("/openapi.json").json()["paths"]["/chat/execute-sql"][
        "post"
    ]

    assert "requestBody" not in operation


def test_preseeded_current_tab_sql_executes_and_returns_typed_result(
    sql_execution_api: SQLExecutionAPIContext,
) -> None:
    browser_id = str(uuid4())
    _set_browser_cookie(sql_execution_api, browser_id)
    stored_sql = "SELECT specialty, SUM(paid_amount) AS total_paid FROM claims GROUP BY specialty"
    _seed_session(
        sql_execution_api,
        browser_id=browser_id,
        tab_id="tab-a",
        sql=stored_sql,
    )

    response = sql_execution_api.client.post(
        "/chat/execute-sql",
        headers={"X-Tab-Id": "tab-a"},
    )

    assert response.status_code == 200
    assert response.json()["chart"]["chart_type"] == "bar"
    assert response.json()["rows"][0]["total_paid"] == "123.45"
    assert response.json()["summary_source"] == "deterministic_fallback"
    assert sql_execution_api.service.execute.call_args.kwargs["final_sql"] == stored_sql


def test_arbitrary_client_sql_override_is_ignored(
    sql_execution_api: SQLExecutionAPIContext,
) -> None:
    browser_id = str(uuid4())
    _set_browser_cookie(sql_execution_api, browser_id)
    _seed_session(
        sql_execution_api,
        browser_id=browser_id,
        tab_id="tab-a",
        sql="SELECT 1 AS safe_value",
    )

    response = sql_execution_api.client.post(
        "/chat/execute-sql",
        headers={"X-Tab-Id": "tab-a"},
        json={"sql": "DELETE FROM claims"},
    )

    assert response.status_code == 200
    call = sql_execution_api.service.execute.call_args
    assert call.kwargs["final_sql"] == "SELECT 1 AS safe_value"
    assert "DELETE" not in call.kwargs["final_sql"]


def test_sql_and_token_mappings_are_isolated_by_tab(
    sql_execution_api: SQLExecutionAPIContext,
) -> None:
    browser_id = str(uuid4())
    _set_browser_cookie(sql_execution_api, browser_id)
    _seed_session(
        sql_execution_api,
        browser_id=browser_id,
        tab_id="tab-a",
        sql="SELECT 'T001' AS member",
        mapping={"T001": "M000001"},
    )
    _seed_session(
        sql_execution_api,
        browser_id=browser_id,
        tab_id="tab-b",
        sql="SELECT 'T001' AS provider",
        mapping={"T001": "P00001"},
    )

    response_a = sql_execution_api.client.post("/chat/execute-sql", headers={"X-Tab-Id": "tab-a"})
    response_b = sql_execution_api.client.post("/chat/execute-sql", headers={"X-Tab-Id": "tab-b"})

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    first_call, second_call = sql_execution_api.service.execute.call_args_list
    assert first_call.kwargs["final_sql"] == "SELECT 'T001' AS member"
    assert first_call.kwargs["token_mappings"][0].original_value == "M000001"
    assert second_call.kwargs["final_sql"] == "SELECT 'T001' AS provider"
    assert second_call.kwargs["token_mappings"][0].original_value == "P00001"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (QueryTimeoutError("raw database timeout"), 504, "query_timeout"),
        (
            QueryDependencyUnavailableError("postgresql://user:secret@host/db"),
            503,
            "query_dependency_unavailable",
        ),
        (QueryExecutionError("postgresql://user:secret@host/db"), 500, "query_execution_failed"),
        (
            SQLTokenResolutionError("missing original M000001"),
            409,
            "sql_token_resolution_failed",
        ),
    ],
)
def test_execution_failures_use_controlled_safe_error_envelopes(
    sql_execution_api: SQLExecutionAPIContext,
    error: Exception,
    status_code: int,
    code: str,
) -> None:
    browser_id = str(uuid4())
    _set_browser_cookie(sql_execution_api, browser_id)
    _seed_session(
        sql_execution_api,
        browser_id=browser_id,
        tab_id="tab-a",
        sql="SELECT 1",
    )
    sql_execution_api.service.execute.side_effect = error

    response = sql_execution_api.client.post(
        "/chat/execute-sql",
        headers={"X-Tab-Id": "tab-a"},
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    response_text = response.text
    assert "secret" not in response_text
    assert "M000001" not in response_text


def test_summary_settings_have_validated_independent_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.sql_result_summary_max_rows == 50
    assert settings.sql_result_summary_max_chars == 12_000
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sql_result_summary_max_rows=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, sql_result_summary_max_chars=0)
