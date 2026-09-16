"""End-to-end forecasting over actual isolated PostgreSQL data."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.query.postgres import PostgresQueryExecutor
from app.forecasting.factory import build_forecasting_agent
from app.metadata.refresh import build_registry
from app.nlp2sql.agent import NLP2SQLAgent
from tests.llm.fakes import FakeLLMClient

pytestmark = pytest.mark.integration

_HISTORY_SQL = """WITH synthetic_history(period, offset_value) AS (VALUES
(DATE '2025-01-01', 0), (DATE '2025-02-01', 1), (DATE '2025-03-01', 2),
(DATE '2025-04-01', 3), (DATE '2025-05-01', 4), (DATE '2025-06-01', 5),
(DATE '2025-07-01', 6), (DATE '2025-08-01', 7), (DATE '2025-09-01', 8),
(DATE '2025-10-01', 9), (DATE '2025-11-01', 10), (DATE '2025-12-01', 11))
SELECT period, ((SELECT COUNT(*) FROM claims) + offset_value)::double precision AS value
FROM synthetic_history
ORDER BY period"""


@pytest.fixture(scope="module")
def forecasting_engine() -> Iterator[Engine]:
    settings = get_settings()
    if settings.query_test_database_url is None:
        pytest.skip("QUERY_TEST_DATABASE_URL is not configured; forecasting integration skipped")
    engine = create_engine(str(settings.query_test_database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("Could not connect to the isolated PostgreSQL QUERY_TEST_DATABASE_URL")
    yield engine
    engine.dispose()


def test_forecasting_uses_actual_registry_and_read_only_postgresql(
    forecasting_engine: Engine,
) -> None:
    executor = PostgresQueryExecutor(forecasting_engine, max_rows=500, timeout_ms=5_000)
    table = executor.execute("SELECT to_regclass('public.claims') AS table_name")
    if table.rows[0]["table_name"] is None:
        pytest.skip("Phase 3 claims table is not present in QUERY_TEST_DATABASE_URL")
    before = executor.execute("SELECT COUNT(*) AS value FROM claims").rows[0]["value"]
    fake = FakeLLMClient(
        structured_payloads=[
            {
                "metric_label": "Monthly claim volume",
                "frequency": "month",
                "horizon_periods": 3,
                "historical_series_question": (
                    "Return the most recent monthly aggregate claim counts as period and value, "
                    "in chronological order through the latest completed month"
                ),
            },
            {"selected_domains": ["claims"]},
            {"selected_tables": ["claims"]},
            {"sql": _HISTORY_SQL},
            {"score": 0.98, "issues": [], "rewrite_guidance": None},
            {
                "summary": (
                    "Monthly aggregate claim volume is projected for three periods; "
                    "uncertainty intervals are approximate."
                )
            },
        ]
    )
    settings = get_settings()
    nlp2sql = NLP2SQLAgent(build_registry(forecasting_engine), fake)
    agent = build_forecasting_agent(settings, fake, nlp2sql, executor)

    result = agent.forecast("Forecast aggregate monthly claim volume for three months")
    after = executor.execute("SELECT COUNT(*) AS value FROM claims").rows[0]["value"]

    assert len(result.historical_points) >= 8
    assert len(result.forecast_points) == 3
    assert result.selected_model in {
        "naive",
        "moving_average",
        "linear_trend",
        "seasonal_naive",
    }
    assert result.selected_model == "linear_trend"
    assert result.backtest_metrics.mae == pytest.approx(0, abs=1e-9)
    assert [point.predicted for point in result.forecast_points] == pytest.approx(
        [before + 12, before + 13, before + 14]
    )
    for point in result.forecast_points:
        assert point.lower_bound == pytest.approx(point.predicted, abs=1e-8)
        assert point.upper_bound == pytest.approx(point.predicted, abs=1e-8)
    assert result.summary
    assert before == after
