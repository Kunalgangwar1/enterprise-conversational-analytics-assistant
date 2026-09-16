"""Application-level advanced tool adapter tests."""

from unittest.mock import MagicMock

from app.advanced_reasoning.models import ToolExecutionStatus
from app.advanced_reasoning.tools import (
    DataDiscoveryTool,
    DataQualityTool,
    ForecastingTool,
    KnowledgeCatalogTool,
    SemanticaTool,
    SQLAnalyticsTool,
    enabled_advanced_tool_names,
)
from app.core.feature_flags import ToolFeatureFlags
from app.data_discovery.models import DatasetRegistration
from app.data_discovery.search import DataDiscoveryService
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
from app.sql_results.models import (
    ChartMetadata,
    ChartType,
    SQLAnalyticsResult,
    SummarySource,
)


def test_sql_tool_reuses_standard_generation_and_execution_services() -> None:
    nlp2sql = MagicMock()
    nlp2sql.generate_sql.return_value = NLP2SQLResult(
        selected_domains=("claims",),
        selected_tables=("claims",),
        initial_sql="SELECT COUNT(*) FROM claims",
        generated_sql="SELECT COUNT(*) FROM claims",
        final_sql="SELECT COUNT(*) FROM claims",
        validation=SQLValidationResult(
            decision=SQLValidationDecision.ACCEPT,
            score=1,
            attempt=1,
        ),
        generation_attempt=1,
        rewrite_count=0,
        llm_call_count=4,
    )
    execution = MagicMock()
    execution.execute.return_value = SQLAnalyticsResult(
        columns=["count"],
        rows=[{"count": 2}],
        row_count=1,
        truncated=False,
        execution_elapsed_ms=1,
        summary="There are two claims.",
        summary_source=SummarySource.DETERMINISTIC,
        chart=ChartMetadata(
            chart_type=ChartType.TABLE,
            title="Claims",
            selection_rule="test",
        ),
    )

    result = SQLAnalyticsTool(nlp2sql, execution).execute("Count claims")

    nlp2sql.generate_sql.assert_called_once_with("Count claims")
    execution.execute.assert_called_once()
    assert result.status is ToolExecutionStatus.SUCCESS
    assert result.structured_payload == {
        "columns": ["count"],
        "row_count": 1,
        "truncated": False,
    }


def test_data_discovery_tool_uses_deterministic_service() -> None:
    service = DataDiscoveryService(
        (
            DatasetRegistration(
                dataset="claims",
                repository="datasets-claims",
                table="claims",
                domain="claims",
                description="Synthetic claim payments.",
                columns={"paid_amount": ("paid",)},
            ),
        ),
        top_k=1,
    )

    result = DataDiscoveryTool(service).execute("find claims")

    assert "datasets-claims" in result.summary
    assert result.structured_payload == {"match_count": 1}


def test_grounded_specialist_adapters_preserve_safe_citation_ids() -> None:
    catalog_agent = MagicMock()
    catalog_agent.answer.return_value = KnowledgeCatalogResult(
        answer="Catalog answer",
        retrieval_method=RetrievalMethod.HYBRID,
        citations=(
            KnowledgeCitation(
                id="catalog-1",
                title="Claims",
                section="Meaning",
                source_path="datasets/claims.md",
            ),
        ),
    )
    dq_agent = MagicMock()
    dq_agent.answer.return_value = DataQualityResult(
        answer="Quality answer",
        citations=(
            DataQualityCitation(
                id="dq-1",
                title="Claims rules",
                topic="claims",
                source_path="rules/claims.md",
            ),
        ),
    )
    semantica_agent = MagicMock()
    semantica_agent.answer.return_value = catalog_agent.answer.return_value

    assert KnowledgeCatalogTool(catalog_agent).execute("catalog").citations == ("catalog-1",)
    assert DataQualityTool(dq_agent).execute("quality").citations == ("dq-1",)
    assert SemanticaTool(semantica_agent).execute("semantica").citations == ("catalog-1",)


def test_tool_flags_expose_implemented_forecasting_when_enabled() -> None:
    flags = ToolFeatureFlags(
        sql=True,
        forecasting=True,
        group_access=True,
        data_discovery=True,
        knowledge_catalog=True,
        semantica=True,
        data_quality=True,
    )

    names = enabled_advanced_tool_names(flags)

    assert names == {
        "sql",
        "forecasting",
        "knowledge_catalog",
        "data_discovery",
        "data_quality",
        "semantica",
    }


def test_forecasting_tool_calls_agent_and_returns_safe_structured_payload() -> None:
    agent = MagicMock()
    agent.forecast.return_value = ForecastResult(
        metric_label="Monthly claims",
        frequency=ForecastFrequency.MONTH,
        horizon_periods=1,
        selected_model="naive",
        backtest_metrics=ForecastMetrics(mae=1, rmse=2, smape=3),
        historical_points=(),
        forecast_points=(
            ForecastPoint(
                period="2025-01-01",
                predicted=4,
                lower_bound=1,
                upper_bound=7,
            ),
        ),
        summary="Approximate forecast.",
        summary_source=SummarySource.LLM,
        chart=ForecastChartMetadata(title="Monthly claims forecast"),
        warnings=("Approximate intervals.",),
    )

    result = ForecastingTool(agent).execute("Forecast monthly claims")

    agent.forecast.assert_called_once_with("Forecast monthly claims", ())
    assert result.status is ToolExecutionStatus.SUCCESS
    assert result.structured_payload is not None
    assert result.structured_payload["selected_model"] == "naive"
