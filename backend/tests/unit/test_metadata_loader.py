"""Unit tests for semantic metadata configuration loading."""

from pathlib import Path

import pytest

from app.metadata.exceptions import MetadataConfigurationError
from app.metadata.loader import load_domains, load_semantic_metadata, load_tables


def test_semantic_catalog_contains_expected_domains_and_tables() -> None:
    domains, tables = load_semantic_metadata()

    assert {domain.name for domain in domains} == {
        "member",
        "provider_network",
        "clinical_encounters",
        "claims",
        "scheduling",
    }
    assert {table.name for table in tables} == {
        "members",
        "providers",
        "facilities",
        "encounters",
        "claims",
        "claim_lines",
        "appointments",
    }


def test_semantic_tables_define_grains_aliases_and_value_hints() -> None:
    tables = {table.name: table for table in load_tables()}

    assert all(table.grain for table in tables.values())
    assert "medical claim" in tables["claims"].aliases
    assert tables["claims"].columns["claim_status"].value_hints == [
        "submitted",
        "pending",
        "paid",
        "denied",
        "adjusted",
    ]
    assert "Primary Care" in tables["providers"].columns["specialty"].value_hints
    assert "no_show" in tables["appointments"].columns["status"].value_hints


def test_domain_table_mappings_match_phase_five_contract() -> None:
    domains = {domain.name: domain for domain in load_domains()}

    assert domains["member"].tables == ["members"]
    assert domains["provider_network"].tables == ["providers", "facilities"]
    assert domains["clinical_encounters"].tables == ["encounters"]
    assert domains["claims"].tables == ["claims", "claim_lines"]
    assert domains["scheduling"].tables == ["appointments"]


def test_duplicate_domain_definitions_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "domains.yaml"
    path.write_text(
        """
domains:
  - name: duplicated
    description: First definition.
    tables: [members]
  - name: duplicated
    description: Second definition.
    tables: [members]
""",
        encoding="utf-8",
    )

    with pytest.raises(MetadataConfigurationError, match="duplicate domain definitions"):
        load_domains(path)


def test_blank_table_grain_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tables.yaml"
    path.write_text(
        """
tables:
  - name: members
    description: Synthetic members.
    grain: "  "
    domains: [member]
""",
        encoding="utf-8",
    )

    with pytest.raises(MetadataConfigurationError, match="grain"):
        load_tables(path)
