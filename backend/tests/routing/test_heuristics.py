"""Tests for deliberately narrow deterministic routing heuristics."""

import pytest

from app.routing.heuristics import route_by_heuristic
from app.routing.models import InternalRoute


@pytest.mark.parametrize(
    ("text", "expected_route"),
    [
        ("How can I request access to the claims dataset?", InternalRoute.GROUP_ACCESS),
        ("I do not have permission to view this table.", InternalRoute.GROUP_ACCESS),
        ("Which group gives me access to this dataset?", InternalRoute.GROUP_ACCESS),
        ("Why are there null values in this dataset?", InternalRoute.DATA_QUALITY),
        ("Is the claims table fresh?", InternalRoute.DATA_QUALITY),
        ("Show me the data-quality rules.", InternalRoute.DATA_QUALITY),
        ("Use Semantica to search for this.", InternalRoute.SEMANTICA),
        ("Find the dataset containing appointment information.", InternalRoute.DATA_DISCOVERY),
        ("What can you do?", InternalRoute.HELP),
        ("Help", InternalRoute.HELP),
        ("What modes are available?", InternalRoute.HELP),
        ("Hello", InternalRoute.CHAT),
        ("good morning!", InternalRoute.CHAT),
        ("Forecast paid claims next quarter.", InternalRoute.FORECASTING),
        ("Predict claim volume next month.", InternalRoute.FORECASTING),
        ("Project appointment volume next year.", InternalRoute.FORECASTING),
    ],
)
def test_high_confidence_heuristic_examples(
    text: str,
    expected_route: InternalRoute,
) -> None:
    decision = route_by_heuristic(text)

    assert decision is not None
    assert decision.route is expected_route
    assert decision.confidence >= 0.95


@pytest.mark.parametrize(
    "text",
    [
        "Explain the semantic meaning of the claims table.",
        "Explain the ontology for claims.",
        "Document the lineage policy for this table.",
        "Show claims from 2026.",
        "Future access controls need review.",
        "The dashboard is missing.",
        "I can access the claims table.",
        "Show total paid claims by specialty.",
    ],
)
def test_ambiguous_or_broad_requests_do_not_trigger_heuristics(text: str) -> None:
    assert route_by_heuristic(text) is None
