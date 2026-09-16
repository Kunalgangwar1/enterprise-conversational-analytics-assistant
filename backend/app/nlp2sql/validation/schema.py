"""SQLGlot scope-based validation against selected physical metadata."""

from collections.abc import Collection

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope

from app.metadata.registry import MetadataRegistry
from app.nlp2sql.exceptions import SQLSchemaValidationError

ColumnSet = frozenset[str] | None


class SchemaGroundingValidator:
    """Validate deterministically resolvable table and column references."""

    def __init__(self, registry: MetadataRegistry) -> None:
        self._table_columns = {
            _normalize(table.name): frozenset(_normalize(column.name) for column in table.columns)
            for table in registry.list_tables()
        }

    def validate(self, sql: str, selected_tables: Collection[str]) -> tuple[str, ...]:
        """Return concise schema findings; an empty tuple means validation passed."""

        try:
            statement = sqlglot.parse_one(sql, read="postgres", error_level=ErrorLevel.RAISE)
            scopes = tuple(traverse_scope(statement))
            source_columns = {id(scope): self._columns_by_source(scope, set()) for scope in scopes}
        except (SqlglotError, ValueError) as exc:
            raise SQLSchemaValidationError("SQL schema analysis failed unexpectedly") from exc

        selected = {_normalize(name) for name in selected_tables}
        issues: list[str] = []
        for scope in scopes:
            sources = source_columns[id(scope)]
            self._validate_physical_tables(scope, selected, issues)
            self._validate_columns(scope, sources, source_columns, issues)
        return tuple(dict.fromkeys(issues))

    def _validate_physical_tables(
        self,
        scope: Scope,
        selected_tables: set[str],
        issues: list[str],
    ) -> None:
        for _alias, (_node, source) in scope.selected_sources.items():
            if not isinstance(source, exp.Table):
                continue
            table_name = _normalize(source.name)
            if table_name not in self._table_columns:
                issues.append(f"Unknown physical table '{table_name}'.")
            elif table_name not in selected_tables:
                issues.append(f"Physical table '{table_name}' is outside the selected table set.")

    def _validate_columns(
        self,
        scope: Scope,
        sources: dict[str, ColumnSet],
        all_sources: dict[int, dict[str, ColumnSet]],
        issues: list[str],
    ) -> None:
        select_aliases = {
            _normalize(name) for name in scope.expression.named_selects if name != "*"
        }
        for column in scope.columns:
            if column.is_star:
                continue
            column_name = _normalize(column.name)
            qualifier = _normalize(column.table) if column.table else ""
            if qualifier:
                resolved = self._resolve_qualified_source(scope, qualifier, all_sources)
                if resolved is _MISSING:
                    issues.append(
                        f"Column qualifier '{qualifier}' does not resolve in this query scope."
                    )
                elif resolved is not None and column_name not in resolved:
                    issues.append(
                        f"Unknown column '{qualifier}.{column_name}' for source '{qualifier}'."
                    )
                continue

            if column_name in select_aliases and _is_output_alias_reference(column, scope):
                continue

            matching_sources = sorted(
                alias
                for alias, columns in sources.items()
                if columns is not None and column_name in columns
            )
            indeterminate_sources = [alias for alias, columns in sources.items() if columns is None]
            if len(matching_sources) == 1 and not indeterminate_sources:
                continue
            if len(matching_sources) > 1:
                joined_sources = ", ".join(matching_sources)
                issues.append(
                    f"Unqualified column '{column_name}' is ambiguous across sources: "
                    f"{joined_sources}."
                )
                continue
            if not matching_sources and not indeterminate_sources:
                issues.append(f"Unknown unqualified column '{column_name}'.")

    def _columns_by_source(self, scope: Scope, seen: set[int]) -> dict[str, ColumnSet]:
        if id(scope) in seen:
            return {}
        next_seen = {*seen, id(scope)}
        sources: dict[str, ColumnSet] = {}
        for alias, (_node, source) in scope.selected_sources.items():
            normalized_alias = _normalize(alias)
            if isinstance(source, exp.Table):
                sources[normalized_alias] = self._table_columns.get(_normalize(source.name))
            else:
                sources[normalized_alias] = self._scope_output_columns(source, next_seen)
        return sources

    def _scope_output_columns(self, scope: Scope, seen: set[int]) -> ColumnSet:
        if scope.outer_columns:
            return frozenset(_normalize(name) for name in scope.outer_columns)

        names: set[str] = set()
        wildcard_sources: set[str] = set()
        has_unqualified_wildcard = False
        for selection in scope.expression.selects:
            if isinstance(selection, exp.Star):
                has_unqualified_wildcard = True
            elif isinstance(selection, exp.Column) and selection.is_star:
                wildcard_sources.add(_normalize(selection.table))
            else:
                output_name = selection.alias_or_name
                if output_name:
                    names.add(_normalize(output_name))

        if not has_unqualified_wildcard and not wildcard_sources:
            return frozenset(names)

        available_sources = self._columns_by_source(scope, seen)
        source_columns = tuple(
            columns
            for alias, columns in available_sources.items()
            if has_unqualified_wildcard or alias in wildcard_sources
        )
        if any(columns is None for columns in source_columns):
            return None
        for columns in source_columns:
            if columns is not None:
                names.update(columns)
        return frozenset(names)

    @staticmethod
    def _resolve_qualified_source(
        scope: Scope,
        qualifier: str,
        all_sources: dict[int, dict[str, ColumnSet]],
    ) -> object | ColumnSet:
        current: Scope | None = scope
        while current is not None:
            sources = all_sources.get(id(current), {})
            if qualifier in sources:
                return sources[qualifier]
            current = current.parent
        return _MISSING


_MISSING = object()


def _normalize(identifier: str) -> str:
    return identifier.casefold()


def _is_output_alias_reference(column: exp.Column, scope: Scope) -> bool:
    ancestor = column.parent
    while ancestor is not None and ancestor is not scope.expression:
        if isinstance(ancestor, (exp.Order, exp.Group)):
            return True
        ancestor = ancestor.parent
    return False
