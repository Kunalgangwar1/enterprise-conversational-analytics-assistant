"""Render deterministic, human-readable context from merged metadata."""

from collections.abc import Iterable

from app.metadata.models import TableMetadata


def build_metadata_context(tables: Iterable[TableMetadata]) -> str:
    """Build context containing only the supplied tables and their metadata."""

    sections = [_render_table(table) for table in sorted(tables, key=lambda item: item.name)]
    return "\n\n".join(sections)


def _render_table(table: TableMetadata) -> str:
    lines = [
        f"TABLE {table.name}",
        f"Description: {table.description}",
        f"Grain: {table.grain}",
        f"Domains: {', '.join(sorted(table.domains))}",
        f"Aliases: {_render_values(table.aliases)}",
        "Columns:",
    ]

    for column in sorted(table.columns, key=lambda item: item.name):
        attributes = [column.data_type]
        attributes.append("nullable" if column.nullable else "not null")
        if column.primary_key:
            attributes.append("primary key")
        if column.unique:
            attributes.append("unique")
        if column.foreign_keys:
            attributes.append(f"references {', '.join(sorted(column.foreign_keys))}")
        lines.append(f"- {column.name} ({'; '.join(attributes)})")
        if column.description:
            lines.append(f"  Description: {column.description}")
        if column.aliases:
            lines.append(f"  Aliases: {', '.join(sorted(column.aliases))}")
        if column.value_hints:
            lines.append(f"  Value hints: {', '.join(column.value_hints)}")
        if column.notes:
            lines.append(f"  Notes: {'; '.join(column.notes)}")

    lines.append("Relationships:")
    if table.relationships:
        for relationship in sorted(
            table.relationships,
            key=lambda item: (
                item.source_columns,
                item.target_table,
                item.target_columns,
            ),
        ):
            source = ", ".join(
                f"{relationship.source_table}.{column}" for column in relationship.source_columns
            )
            target = ", ".join(
                f"{relationship.target_table}.{column}" for column in relationship.target_columns
            )
            lines.append(f"- {source} -> {target}")
    else:
        lines.append("- none")

    if table.notes:
        lines.append("Analytical notes:")
        lines.extend(f"- {note}" for note in table.notes)
    return "\n".join(lines)


def _render_values(values: list[str]) -> str:
    return ", ".join(sorted(values)) if values else "none"
