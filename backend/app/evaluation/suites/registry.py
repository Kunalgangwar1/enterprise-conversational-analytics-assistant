"""Stable suite-name to evaluator mapping."""

from app.evaluation.suites import (
    advanced_reasoning,
    data_discovery,
    data_quality,
    forecasting,
    knowledge_catalog,
    multihop,
    nlp2sql,
    orchestration,
    privacy,
    routing,
    semantica,
    sql_safety,
)

SUITE_EVALUATORS = {
    "routing": routing.evaluate,
    "nlp2sql": nlp2sql.evaluate,
    "sql_safety": sql_safety.evaluate,
    "data_discovery": data_discovery.evaluate,
    "knowledge_catalog": knowledge_catalog.evaluate,
    "data_quality": data_quality.evaluate,
    "semantica": semantica.evaluate,
    "advanced_reasoning": advanced_reasoning.evaluate,
    "multihop": multihop.evaluate,
    "forecasting": forecasting.evaluate,
    "orchestration": orchestration.evaluate,
    "privacy": privacy.evaluate,
}
