"""Optional configured live smoke for the internal forecasting workflow."""

import argparse

from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.query.exceptions import QueryConfigurationError
from app.db.query.postgres import PostgresQueryExecutor
from app.db.session import create_database_engine
from app.forecasting.factory import build_forecasting_agent
from app.llm.factory import create_llm_client
from app.metadata.refresh import build_registry
from app.nlp2sql.agent import NLP2SQLAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one internal aggregate forecast smoke")
    parser.add_argument("question", help="Privacy-safe aggregate operational forecast question")
    args = parser.parse_args()
    settings = get_settings()
    if settings.query_database_url is None:
        raise QueryConfigurationError("QUERY_DATABASE_URL is required for forecast smoke")

    metadata_engine = create_database_engine(str(settings.database_url))
    query_engine = create_engine(str(settings.query_database_url), pool_pre_ping=True)
    try:
        llm_client = create_llm_client(settings)
        executor = PostgresQueryExecutor(
            query_engine,
            max_rows=settings.query_max_rows,
            timeout_ms=settings.query_timeout_ms,
        )
        nlp2sql = NLP2SQLAgent(build_registry(metadata_engine), llm_client)
        result = build_forecasting_agent(settings, llm_client, nlp2sql, executor).forecast(
            args.question
        )
        print(f"metric={result.metric_label}")
        print(f"frequency={result.frequency.value}")
        print(f"history_points={len(result.historical_points)}")
        print(f"selected_model={result.selected_model}")
        print(result.backtest_metrics.model_dump_json())
        for point in result.forecast_points:
            print(point.model_dump_json())
        print(result.summary)
    finally:
        query_engine.dispose()
        metadata_engine.dispose()


if __name__ == "__main__":
    main()
