"""Tests for domain-derived table candidates and relationship grounding."""

import pytest

from app.metadata.models import TableMetadata
from app.metadata.registry import MetadataRegistry
from app.nlp2sql.exceptions import TableSelectionError
from app.nlp2sql.selectors import TableSelector
from tests.llm.fakes import FakeLLMClient


def _candidate_tables(
    registry: MetadataRegistry,
    *domains: str,
) -> tuple[TableMetadata, ...]:
    names = sorted(
        {table.name for domain in domains for table in registry.tables_for_domain(domain)}
    )
    return tuple(registry.get_table(name) for name in names)


def _select(
    registry: MetadataRegistry,
    selected_tables: list[str],
    domains: tuple[str, ...],
    *,
    max_tables: int = 5,
) -> tuple[tuple[str, ...], FakeLLMClient]:
    fake = FakeLLMClient(structured_payload={"selected_tables": selected_tables})
    selected = TableSelector(fake, max_tables=max_tables).select(
        "Show paid claims by facility type.",
        _candidate_tables(registry, *domains),
    )
    return selected, fake


def test_claims_domain_exposes_claim_and_claim_line_candidates(
    metadata_registry: MetadataRegistry,
) -> None:
    names = [table.name for table in _candidate_tables(metadata_registry, "claims")]

    assert names == ["claim_lines", "claims"]


def test_provider_network_exposes_provider_and_facility_candidates(
    metadata_registry: MetadataRegistry,
) -> None:
    names = [table.name for table in _candidate_tables(metadata_registry, "provider_network")]

    assert names == ["facilities", "providers"]


@pytest.mark.parametrize(
    "selected_tables",
    [
        ["claims", "providers"],
        ["claims", "providers", "facilities"],
    ],
)
def test_cross_domain_questions_can_select_joinable_tables(
    metadata_registry: MetadataRegistry,
    selected_tables: list[str],
) -> None:
    selected, _ = _select(
        metadata_registry,
        selected_tables,
        ("claims", "provider_network"),
    )

    assert selected == tuple(selected_tables)


@pytest.mark.parametrize(
    ("selected_tables", "domains", "maximum", "message"),
    [
        (["invented_table"], ("claims",), 5, "non-candidate"),
        (["facilities"], ("claims",), 5, "non-candidate"),
        ([], ("claims",), 5, "cannot be empty"),
        (["claims", "claim_lines"], ("claims",), 1, "configured maximum"),
    ],
)
def test_invalid_table_selection_fails_clearly(
    metadata_registry: MetadataRegistry,
    selected_tables: list[str],
    domains: tuple[str, ...],
    maximum: int,
    message: str,
) -> None:
    with pytest.raises(TableSelectionError, match=message):
        _select(
            metadata_registry,
            selected_tables,
            domains,
            max_tables=maximum,
        )


def test_table_prompt_contains_grain_and_candidate_relationships_not_full_columns(
    metadata_registry: MetadataRegistry,
) -> None:
    _, fake = _select(
        metadata_registry,
        ["claims", "providers", "facilities"],
        ("claims", "provider_network"),
    )
    grounding = fake.requests[0].messages[1].content

    assert "grain: One row per synthetic healthcare claim." in grounding
    assert "claims.provider_id -> providers.id" in grounding
    assert "providers.facility_id -> facilities.id" in grounding
    assert "paid_amount" not in grounding
    assert "Columns:" not in grounding
