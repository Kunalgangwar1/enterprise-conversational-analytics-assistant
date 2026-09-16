"""PostgreSQL SQL AST validation for the read-only execution boundary."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from app.db.query.exceptions import QueryValidationError, QueryValidationReason

_FORBIDDEN_NODE_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Alter,
    exp.Drop,
    exp.TruncateTable,
    exp.Copy,
    exp.Command,
    exp.Into,
    exp.Lock,
    exp.Grant,
    exp.Revoke,
    exp.Set,
    exp.Transaction,
)


def validate_read_only_sql(sql: str) -> None:
    """Require exactly one fully read-only PostgreSQL query expression."""
    if not sql.strip():
        raise QueryValidationError("SQL must not be blank.", reason=QueryValidationReason.BLANK)

    try:
        statements = sqlglot.parse(sql, read="postgres", error_level=ErrorLevel.RAISE)
    except SqlglotError as exc:
        raise QueryValidationError(
            "SQL could not be parsed as PostgreSQL.",
            reason=QueryValidationReason.PARSE_ERROR,
        ) from exc

    if len(statements) != 1 or statements[0] is None:
        raise QueryValidationError(
            "Exactly one SQL statement is required.",
            reason=QueryValidationReason.MULTIPLE_STATEMENTS,
        )

    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise QueryValidationError(
            "Only read-only query expressions are allowed.",
            reason=QueryValidationReason.NON_QUERY,
        )

    forbidden_node = next(
        (node for node in statement.walk() if isinstance(node, _FORBIDDEN_NODE_TYPES)),
        None,
    )
    if forbidden_node is not None:
        raise QueryValidationError(
            "The SQL statement contains a forbidden operation.",
            reason=QueryValidationReason.FORBIDDEN_OPERATION,
        )
