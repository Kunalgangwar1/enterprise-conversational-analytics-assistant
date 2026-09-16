"""Unit tests for complete-AST read-only SQL validation."""

import pytest

from app.db.query.exceptions import QueryValidationError
from app.db.query.guard import validate_read_only_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM claims",
        "SELECT claim_status, COUNT(*) FROM claims GROUP BY claim_status",
        "WITH recent AS (SELECT * FROM claims) SELECT * FROM recent",
        "SELECT 1 UNION SELECT 2",
        "SELECT 1 INTERSECT SELECT 1",
        "SELECT 1 EXCEPT SELECT 2",
    ],
)
def test_read_only_query_expressions_are_allowed(sql: str) -> None:
    validate_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "SELECT * FROM",
        "INSERT INTO claims (claim_external_id) VALUES ('C1')",
        "UPDATE claims SET claim_status = 'paid'",
        "DELETE FROM claims",
        "MERGE INTO claims USING other_claims ON claims.id = other_claims.id "
        "WHEN MATCHED THEN DELETE",
        "DROP TABLE claims",
        "CREATE TABLE copied_claims (id INTEGER)",
        "ALTER TABLE claims ADD COLUMN unsafe INTEGER",
        "TRUNCATE TABLE claims",
        "SELECT * INTO copied_claims FROM claims",
        "SELECT 1; DROP TABLE claims",
        "WITH removed AS (DELETE FROM claims RETURNING *) SELECT * FROM removed",
        "SELECT * FROM claims FOR UPDATE",
        "SELECT * FROM claims FOR SHARE",
        "COPY claims TO STDOUT",
        "CALL unsafe_procedure()",
        "DO $$ BEGIN NULL; END $$",
    ],
)
def test_non_read_only_or_invalid_statements_are_rejected(sql: str) -> None:
    with pytest.raises(QueryValidationError):
        validate_read_only_sql(sql)
