"""HTTP contracts and session isolation for aggregate dashboard endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.dashboards.service import DashboardService
from app.main import create_app
from app.sessions.identity import SessionIdentity
from app.sessions.json_store import JsonFileSessionStore
from app.sessions.models import ChatMessage, ChatRole
from tests.dashboards.fakes import StubDashboardRepository


def _application(
    tmp_path: Path,
) -> tuple[TestClient, JsonFileSessionStore, StubDashboardRepository]:
    repository = StubDashboardRepository()
    store = JsonFileSessionStore(tmp_path / "sessions")
    settings = Settings(
        _env_file=None,
        app_env="test",
        artifacts_output_dir=tmp_path,
        gemini_api_key=None,
        azure_openai_api_key=None,
    )
    app = create_app(
        settings,
        session_store=store,
        dashboard_service=DashboardService(repository),
    )
    return TestClient(app), store, repository


def test_dashboard_endpoint_family_exists(tmp_path: Path) -> None:
    client, _, _ = _application(tmp_path)
    paths = client.app.openapi()["paths"]
    assert {
        "/api/dashboards/overview",
        "/api/dashboards/claims",
        "/api/dashboards/operations",
    }.issubset(paths)


def test_dashboard_endpoints_need_no_model_or_cloud_credentials(tmp_path: Path) -> None:
    client, _, _ = _application(tmp_path)
    with client:
        responses = [
            client.get("/api/dashboards/overview"),
            client.get("/api/dashboards/claims"),
            client.get("/api/dashboards/operations"),
        ]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["data_as_of"] == "2025-12-31"


def test_invalid_dashboard_dates_use_safe_error_envelope(tmp_path: Path) -> None:
    client, _, _ = _application(tmp_path)
    with client:
        malformed_start = client.get("/api/dashboards/overview", params={"start_date": "bad-date"})
        malformed_end = client.get("/api/dashboards/claims", params={"end_date": "bad-date"})
        reversed_range = client.get(
            "/api/dashboards/operations",
            params={"start_date": "2025-02-01", "end_date": "2025-01-01"},
        )

    for response in (malformed_start, malformed_end, reversed_range):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_dashboard_date_range"
        assert "Traceback" not in response.text


def test_dashboard_has_no_arbitrary_sql_contract(tmp_path: Path) -> None:
    client, _, repository = _application(tmp_path)
    with client:
        response = client.get(
            "/api/dashboards/overview",
            params={"sql": "DELETE FROM claims"},
        )
        method_not_allowed = client.post(
            "/api/dashboards/overview",
            json={"sql": "SELECT * FROM members"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_dashboard_parameters"
    assert method_not_allowed.status_code == 405
    assert all(call[0] in {"availability", "overview"} for call in repository.calls)


def test_dashboard_requests_do_not_mutate_chat_session(tmp_path: Path) -> None:
    client, store, _ = _application(tmp_path)
    settings = Settings(_env_file=None, app_env="test", artifacts_output_dir=tmp_path)
    tab_id = "dashboard-isolation"

    with client:
        selected = client.post(
            "/chat/select-mode",
            json={"mode": "sql"},
            headers={"X-Tab-Id": tab_id},
        )
        identity = SessionIdentity(
            browser_session_id=client.cookies.get(settings.session_cookie_name),
            tab_id=tab_id,
            owner_subject="dev-user",
        )
        before = store.load(identity)
        assert before is not None
        populated = before.model_copy(
            update={
                "chat_history": [ChatMessage(role=ChatRole.USER, content="Synthetic question")],
                "last_generated_sql": "SELECT 1",
                "last_token_mapping": {"T001": "C0000001"},
            }
        )
        store.save(populated)
        dashboard = client.get(
            "/api/dashboards/overview",
            headers={"X-Tab-Id": tab_id},
        )
        after = store.load(identity)

    assert selected.status_code == dashboard.status_code == 200
    assert after == populated
