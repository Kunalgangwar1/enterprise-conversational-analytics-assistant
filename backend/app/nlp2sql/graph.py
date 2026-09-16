"""LangGraph construction for validation and one controlled SQL rewrite."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.nlp2sql.models import SQLValidationDecision
from app.nlp2sql.nodes import NLP2SQLNodes
from app.nlp2sql.state import NLP2SQLState

NLP2SQL_NODE_SEQUENCE = (
    "refresh_metadata",
    "select_domains",
    "select_tables",
    "build_metadata",
    "generate_sql",
    "validate_sql",
    "regenerate_sql",
)


def route_after_validation(state: NLP2SQLState) -> str:
    """Route from the typed decision; validation enforces the rewrite budget."""

    return state["validation_result"].decision.value


def build_nlp2sql_graph(nodes: NLP2SQLNodes) -> CompiledStateGraph:
    """Compile validation branches with one explicit regeneration cycle."""

    builder = StateGraph(NLP2SQLState)
    builder.add_node("refresh_metadata", nodes.refresh_metadata)
    builder.add_node("select_domains", nodes.select_domains)
    builder.add_node("select_tables", nodes.select_tables)
    builder.add_node("build_metadata", nodes.build_metadata)
    builder.add_node("generate_sql", nodes.generate_sql)
    builder.add_node("validate_sql", nodes.validate_sql)
    builder.add_node("regenerate_sql", nodes.regenerate_sql)

    builder.add_edge(START, "refresh_metadata")
    builder.add_edge("refresh_metadata", "select_domains")
    builder.add_edge("select_domains", "select_tables")
    builder.add_edge("select_tables", "build_metadata")
    builder.add_edge("build_metadata", "generate_sql")
    builder.add_edge("generate_sql", "validate_sql")
    builder.add_conditional_edges(
        "validate_sql",
        route_after_validation,
        {
            SQLValidationDecision.ACCEPT.value: END,
            SQLValidationDecision.REJECT.value: END,
            SQLValidationDecision.REWRITE.value: "regenerate_sql",
        },
    )
    builder.add_edge("regenerate_sql", "validate_sql")
    return builder.compile(name="standard_nlp2sql_validation")
