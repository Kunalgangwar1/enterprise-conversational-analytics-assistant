"""Fixed instructions and compact metadata grounding for NLP-to-SQL stages."""

from collections.abc import Iterable

from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.metadata.models import DomainMetadata, TableMetadata

DOMAIN_SELECTION_SYSTEM_PROMPT = """Select the minimum set of business domains needed to answer
the user's analytical question. Select only names from the supplied domain catalog. Do not answer
the business question and do not generate SQL. Return only the requested structured schema."""

TABLE_SELECTION_SYSTEM_PROMPT = """Select the minimum sufficient set of tables from the supplied
candidate catalog. Select only supplied table names, include bridge tables needed for joins, pay
attention to table grain and direct relationships, and do not generate SQL. Return only the
requested structured schema."""

SQL_GENERATION_SYSTEM_PROMPT = """Generate exactly one PostgreSQL read-only SELECT or WITH query.
Use only supplied tables and columns, use supplied foreign-key relationships, never invent schema
objects, use explicit join conditions, avoid SELECT * where practical, respect documented table
grain, and preserve the semantic meaning of measures. Do not emit INSERT, UPDATE, DELETE, MERGE,
CREATE, ALTER, DROP, TRUNCATE, COPY, or procedure calls. Return only the requested structured
schema with SQL and no Markdown fences or explanation. This prompt is not an execution security
boundary; later validation must approve generated SQL before it can run."""

SQL_SEMANTIC_VALIDATION_SYSTEM_PROMPT = """Assess whether the supplied PostgreSQL query correctly
answers the user's analytical question using only the supplied metadata. Evaluate requested
dimensions, measures, filters, aggregations, grouping, joins, table grain, double-counting risk,
temporal interpretation, ordering, and top-N intent where applicable. Do not execute SQL, change
schema, invent business semantics, or return a workflow decision. Return only the requested score,
concise issues, and optional rewrite guidance. Do not provide hidden reasoning or
chain-of-thought."""

SQL_REWRITE_SYSTEM_PROMPT = """Correct the supplied PostgreSQL query using the validation findings.
Remain within exactly the same selected schema and do not add unrelated tables. Return exactly one
read-only PostgreSQL SELECT or WITH query using documented columns and joins. Do not execute SQL or
emit Markdown, explanations, INSERT, UPDATE, DELETE, DDL, commands, or locking clauses. Return only
the requested structured schema."""


def build_domain_selection_request(
    safe_question: str,
    domains: Iterable[DomainMetadata],
) -> LLMRequest:
    """Build a role-separated request with compact domain-only grounding."""

    lines = ["AVAILABLE DOMAINS:"]
    for domain in sorted(domains, key=lambda item: item.name):
        aliases = ", ".join(sorted(domain.aliases)) if domain.aliases else "none"
        lines.append(f"- {domain.name}: {domain.description} | aliases: {aliases}")
    return _structured_request(DOMAIN_SELECTION_SYSTEM_PROMPT, "\n".join(lines), safe_question)


def build_table_selection_request(
    safe_question: str,
    tables: Iterable[TableMetadata],
) -> LLMRequest:
    """Build compact candidate-table grounding without full column schemas."""

    ordered_tables = tuple(sorted(tables, key=lambda item: item.name))
    candidate_names = {table.name for table in ordered_tables}
    lines = ["CANDIDATE TABLES:"]
    for table in ordered_tables:
        aliases = ", ".join(sorted(table.aliases)) if table.aliases else "none"
        lines.append(
            f"- {table.name}: {table.description} | grain: {table.grain} | aliases: {aliases}"
        )
        for relationship in sorted(
            table.relationships,
            key=lambda item: (item.source_columns, item.target_table, item.target_columns),
        ):
            if relationship.target_table not in candidate_names:
                continue
            source = ", ".join(
                f"{relationship.source_table}.{column}" for column in relationship.source_columns
            )
            target = ", ".join(
                f"{relationship.target_table}.{column}" for column in relationship.target_columns
            )
            lines.append(f"  relationship: {source} -> {target}")
    return _structured_request(TABLE_SELECTION_SYSTEM_PROMPT, "\n".join(lines), safe_question)


def build_sql_generation_request(
    safe_question: str,
    metadata_context: str,
) -> LLMRequest:
    """Build a PostgreSQL generation request grounded in selected-table metadata."""

    grounding = f"SELECTED POSTGRESQL METADATA:\n{metadata_context}"
    return _structured_request(SQL_GENERATION_SYSTEM_PROMPT, grounding, safe_question)


def build_sql_semantic_validation_request(
    *,
    safe_question: str,
    selected_domains: tuple[str, ...],
    selected_tables: tuple[str, ...],
    metadata_context: str,
    generated_sql: str,
) -> LLMRequest:
    """Build semantic assessment input while keeping the safe question as user content."""

    grounding = (
        f"SELECTED DOMAINS: {', '.join(selected_domains)}\n"
        f"SELECTED TABLES: {', '.join(selected_tables)}\n"
        f"SELECTED POSTGRESQL METADATA:\n{metadata_context}\n"
        f"SQL CANDIDATE:\n{generated_sql}"
    )
    return _structured_request(
        SQL_SEMANTIC_VALIDATION_SYSTEM_PROMPT,
        grounding,
        safe_question,
    )


def build_sql_rewrite_request(
    *,
    safe_question: str,
    selected_domains: tuple[str, ...],
    selected_tables: tuple[str, ...],
    metadata_context: str,
    previous_sql: str,
    validation_issues: tuple[str, ...],
    rewrite_guidance: str | None,
) -> LLMRequest:
    """Build one controlled correction request without schema reselection."""

    issue_lines = "\n".join(f"- {issue}" for issue in validation_issues) or "- none supplied"
    guidance = rewrite_guidance or "Correct all listed defects within the selected schema."
    grounding = (
        f"SELECTED DOMAINS: {', '.join(selected_domains)}\n"
        f"SELECTED TABLES: {', '.join(selected_tables)}\n"
        f"SELECTED POSTGRESQL METADATA:\n{metadata_context}\n"
        f"PREVIOUS SQL:\n{previous_sql}\n"
        f"VALIDATION ISSUES:\n{issue_lines}\n"
        f"CORRECTION GUIDANCE:\n{guidance}"
    )
    return _structured_request(SQL_REWRITE_SYSTEM_PROMPT, grounding, safe_question)


def _structured_request(system_prompt: str, grounding: str, safe_question: str) -> LLMRequest:
    return LLMRequest(
        messages=[
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.SYSTEM, content=grounding),
            LLMMessage(role=LLMRole.USER, content=safe_question),
        ],
        temperature=0,
    )
