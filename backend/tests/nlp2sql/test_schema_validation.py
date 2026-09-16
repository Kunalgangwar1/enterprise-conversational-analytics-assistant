"""Deterministic SQLGlot schema-grounding tests over Phase 5 metadata."""

import pytest

from app.metadata.registry import MetadataRegistry
from app.nlp2sql.validation.schema import SchemaGroundingValidator


@pytest.mark.parametrize(
    ("sql", "selected_tables"),
    [
        ("SELECT paid_amount FROM claims", ["claims"]),
        ("SELECT c.paid_amount FROM claims AS c", ["claims"]),
        (
            "WITH paid AS (SELECT provider_id, paid_amount FROM claims) SELECT * FROM paid",
            ["claims"],
        ),
        (
            "WITH paid AS (SELECT * FROM claims) SELECT paid.provider_id FROM paid",
            ["claims"],
        ),
        (
            "WITH paid AS ("
            "SELECT c.* FROM claims AS c JOIN providers AS p ON p.id = c.provider_id"
            ") SELECT paid.provider_id FROM paid",
            ["claims", "providers"],
        ),
        (
            "WITH paid(provider, amount) AS "
            "(SELECT provider_id, paid_amount FROM claims) "
            "SELECT paid.provider, amount FROM paid",
            ["claims"],
        ),
        (
            "SELECT SUM(c.paid_amount) AS total_paid FROM claims AS c ORDER BY total_paid DESC",
            ["claims"],
        ),
        (
            "SELECT paid_amount FROM claims AS c JOIN providers AS p ON p.id = c.provider_id",
            ["claims", "providers"],
        ),
        (
            "SELECT f.facility_type, SUM(c.paid_amount) FROM claims AS c "
            "JOIN providers AS p ON p.id = c.provider_id "
            "JOIN facilities AS f ON f.id = p.facility_id "
            "GROUP BY f.facility_type",
            ["claims", "providers", "facilities"],
        ),
    ],
)
def test_selected_tables_columns_aliases_ctes_and_bridge_joins_validate(
    metadata_registry: MetadataRegistry,
    sql: str,
    selected_tables: list[str],
) -> None:
    validator = SchemaGroundingValidator(metadata_registry)

    assert validator.validate(sql, selected_tables) == ()


@pytest.mark.parametrize(
    ("sql", "selected_tables", "expected_issue"),
    [
        ("SELECT * FROM invented", ["claims"], "Unknown physical table 'invented'"),
        (
            "SELECT m.id FROM members AS m",
            ["claims"],
            "outside the selected table set",
        ),
        (
            "SELECT c.invented_column FROM claims AS c",
            ["claims"],
            "Unknown column 'c.invented_column'",
        ),
        (
            "SELECT invented_column FROM claims",
            ["claims"],
            "Unknown unqualified column 'invented_column'",
        ),
        (
            "SELECT id FROM claims AS c JOIN providers AS p ON p.id = c.provider_id",
            ["claims", "providers"],
            "ambiguous across sources: c, p",
        ),
        (
            "WITH paid AS ("
            "SELECT c.* FROM claims AS c JOIN providers AS p ON p.id = c.provider_id"
            ") SELECT paid.specialty FROM paid",
            ["claims", "providers"],
            "Unknown column 'paid.specialty'",
        ),
    ],
)
def test_schema_hallucinations_and_ambiguity_produce_findings(
    metadata_registry: MetadataRegistry,
    sql: str,
    selected_tables: list[str],
    expected_issue: str,
) -> None:
    issues = SchemaGroundingValidator(metadata_registry).validate(sql, selected_tables)

    assert any(expected_issue in issue for issue in issues)
