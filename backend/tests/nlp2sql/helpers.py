"""Deterministic fake builders shared by NLP-to-SQL tests."""

from tests.llm.fakes import FakeLLMClient

SPECIALTY_SQL = (
    "SELECT p.specialty, SUM(c.paid_amount) AS total_paid "
    "FROM claims AS c JOIN providers AS p ON p.id = c.provider_id "
    "GROUP BY p.specialty ORDER BY total_paid DESC"
)

FACILITY_SQL = (
    "SELECT f.facility_type, SUM(c.paid_amount) AS total_paid "
    "FROM claims AS c JOIN providers AS p ON p.id = c.provider_id "
    "JOIN facilities AS f ON f.id = p.facility_id "
    "GROUP BY f.facility_type ORDER BY total_paid DESC"
)


def workflow_fake(
    *,
    domains: list[str] | None = None,
    tables: list[str] | None = None,
    sql: str = SPECIALTY_SQL,
    semantic_score: float = 0.95,
    semantic_issues: list[str] | None = None,
    rewrite_guidance: str | None = None,
) -> FakeLLMClient:
    """Configure the direct-accept responses used by one graph invocation."""

    return FakeLLMClient(
        structured_payloads=[
            {"selected_domains": domains or ["claims", "provider_network"]},
            {"selected_tables": tables or ["claims", "providers"]},
            {"sql": sql},
            {
                "score": semantic_score,
                "issues": semantic_issues or [],
                "rewrite_guidance": rewrite_guidance,
            },
        ]
    )
