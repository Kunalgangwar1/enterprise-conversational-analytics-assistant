"""Structured multi-hop plan validation tests."""

import pytest

from app.llm.exceptions import LLMProviderError
from app.nlp2sql.multihop.exceptions import MultiHopPlanningError
from app.nlp2sql.multihop.models import MultiHopPlan
from app.nlp2sql.multihop.planner import MultiHopPlanner, validate_multihop_plan
from tests.llm.fakes import FakeLLMClient


def _plan(*hops: dict[str, object]) -> MultiHopPlan:
    return MultiHopPlan.model_validate({"hops": list(hops)})


def test_one_hop_and_dependent_plan_are_valid_and_deterministic() -> None:
    one = _plan(
        {"hop_id": "h1", "sub_question": "Count claims", "depends_on": [], "purpose": "Count"}
    )
    dependent = _plan(
        {
            "hop_id": "h2",
            "sub_question": "Compare winner",
            "depends_on": ["h1"],
            "purpose": "Compare",
        },
        {"hop_id": "h1", "sub_question": "Find winner", "depends_on": [], "purpose": "Rank"},
    )

    assert [item.hop_id for item in validate_multihop_plan(one, max_hops=3)] == ["h1"]
    assert [item.hop_id for item in validate_multihop_plan(dependent, max_hops=3)] == ["h1", "h2"]


def test_plan_above_max_hops_is_rejected() -> None:
    plan = _plan(
        {"hop_id": "h1", "sub_question": "One", "depends_on": [], "purpose": "One"},
        {"hop_id": "h2", "sub_question": "Two", "depends_on": [], "purpose": "Two"},
    )
    with pytest.raises(MultiHopPlanningError, match="hop budget"):
        validate_multihop_plan(plan, max_hops=1)


def test_unknown_and_cyclic_dependencies_are_rejected() -> None:
    unknown = _plan(
        {"hop_id": "h1", "sub_question": "One", "depends_on": ["missing"], "purpose": "One"}
    )
    cyclic = _plan(
        {"hop_id": "h1", "sub_question": "One", "depends_on": ["h2"], "purpose": "One"},
        {"hop_id": "h2", "sub_question": "Two", "depends_on": ["h1"], "purpose": "Two"},
    )
    with pytest.raises(MultiHopPlanningError, match="unknown dependency"):
        validate_multihop_plan(unknown, max_hops=3)
    with pytest.raises(MultiHopPlanningError, match="cycle"):
        validate_multihop_plan(cyclic, max_hops=3)


def test_planner_output_cannot_supply_raw_sql() -> None:
    fake = FakeLLMClient(
        structured_payload={
            "hops": [
                {
                    "hop_id": "h1",
                    "sub_question": "Count claims",
                    "depends_on": [],
                    "purpose": "Count",
                    "sql": "SELECT * FROM claims",
                }
            ]
        }
    )

    with pytest.raises(MultiHopPlanningError, match="structured output"):
        MultiHopPlanner(fake, max_hops=3).create_plan("Safe question")


def test_hop_sub_question_cannot_be_raw_sql() -> None:
    plan = _plan(
        {
            "hop_id": "h1",
            "sub_question": "SELECT * FROM claims",
            "depends_on": [],
            "purpose": "Count",
        }
    )

    with pytest.raises(MultiHopPlanningError, match="executable"):
        validate_multihop_plan(plan, max_hops=3)


def test_planning_provider_failure_does_not_fabricate_plan() -> None:
    class FailingLLM:
        def generate_structured(self, request, response_model):
            raise LLMProviderError("provider unavailable")

    with pytest.raises(MultiHopPlanningError, match="structured output"):
        MultiHopPlanner(FailingLLM(), max_hops=3).create_plan("Safe question")
