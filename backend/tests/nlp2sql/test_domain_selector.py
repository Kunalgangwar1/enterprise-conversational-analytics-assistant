"""Tests for compact, structured domain selection."""

import pytest

from app.llm.models import LLMRole
from app.metadata.registry import MetadataRegistry
from app.nlp2sql.exceptions import DomainSelectionError
from app.nlp2sql.selectors import DomainSelector
from tests.llm.fakes import FakeLLMClient


def _select(
    registry: MetadataRegistry,
    selected_domains: list[str],
    *,
    max_domains: int = 3,
) -> tuple[tuple[str, ...], FakeLLMClient]:
    fake = FakeLLMClient(structured_payload={"selected_domains": selected_domains})
    selected = DomainSelector(fake, max_domains=max_domains).select(
        "Show total paid claims by specialty.",
        registry.list_domains(),
    )
    return selected, fake


def test_claims_question_can_select_claims_domain(metadata_registry: MetadataRegistry) -> None:
    selected, _ = _select(metadata_registry, ["claims"])

    assert selected == ("claims",)


def test_cross_domain_question_can_select_claims_and_provider_network(
    metadata_registry: MetadataRegistry,
) -> None:
    selected, _ = _select(metadata_registry, ["claims", "provider_network"])

    assert selected == ("claims", "provider_network")


def test_duplicate_domains_are_normalized_in_first_occurrence_order(
    metadata_registry: MetadataRegistry,
) -> None:
    selected, _ = _select(metadata_registry, ["claims", "claims", "provider_network"])

    assert selected == ("claims", "provider_network")


@pytest.mark.parametrize(
    ("selected_domains", "maximum", "message"),
    [
        (["invented_domain"], 3, "unavailable"),
        ([], 3, "cannot be empty"),
        (["claims", "provider_network"], 1, "configured maximum"),
    ],
)
def test_invalid_domain_selection_fails_clearly(
    metadata_registry: MetadataRegistry,
    selected_domains: list[str],
    maximum: int,
    message: str,
) -> None:
    with pytest.raises(DomainSelectionError, match=message):
        _select(metadata_registry, selected_domains, max_domains=maximum)


def test_domain_prompt_contains_only_compact_domain_metadata(
    metadata_registry: MetadataRegistry,
) -> None:
    _, fake = _select(metadata_registry, ["claims"])
    request = fake.requests[0]
    grounding = request.messages[1]

    assert request.messages[0].role is LLMRole.SYSTEM
    assert grounding.role is LLMRole.SYSTEM
    assert request.messages[2].role is LLMRole.USER
    assert request.messages[2].content == "Show total paid claims by specialty."
    assert "claims:" in grounding.content
    assert "provider_network:" in grounding.content
    assert "TABLE claims" not in grounding.content
    assert "paid_amount" not in grounding.content
    assert "Columns:" not in grounding.content
