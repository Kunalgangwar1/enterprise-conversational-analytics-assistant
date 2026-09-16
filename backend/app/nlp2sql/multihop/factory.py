"""Construction of multi-hop over existing application dependencies."""

from app.core.config import Settings
from app.core.feature_flags import ReasoningFeatureFlags
from app.db.query.base import QueryExecutor
from app.llm.base import LLMClient
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.multihop.agent import MultiHopNLP2SQLAgent


def build_multihop_agent(
    *,
    settings: Settings,
    flags: ReasoningFeatureFlags,
    llm_client: LLMClient,
    nlp2sql_agent: NLP2SQLAgent,
    query_executor: QueryExecutor,
) -> MultiHopNLP2SQLAgent:
    """Apply existing feature flags and result-preview settings to one agent."""

    return MultiHopNLP2SQLAgent(
        enabled=flags.nlp2sql_multihop_enabled,
        llm_client=llm_client,
        nlp2sql_agent=nlp2sql_agent,
        query_executor=query_executor,
        max_hops=flags.nlp2sql_multihop_max_hops,
        max_rows_per_hop=flags.nlp2sql_multihop_max_rows_per_hop,
        total_row_budget=flags.nlp2sql_multihop_total_row_budget,
        total_timeout_seconds=flags.nlp2sql_multihop_total_timeout_seconds,
        query_timeout_ms=settings.query_timeout_ms,
        preview_max_rows=settings.sql_result_summary_max_rows,
        preview_max_chars=settings.sql_result_summary_max_chars,
    )
