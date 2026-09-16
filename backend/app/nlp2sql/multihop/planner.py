"""Structured multi-hop planning and deterministic dependency validation."""

from pydantic import ValidationError

from app.advanced_reasoning.security import contains_disallowed_executable_content
from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.nlp2sql.multihop.exceptions import MultiHopPlanningError
from app.nlp2sql.multihop.models import HopPlan, MultiHopPlan

_SYSTEM_PROMPT = """Create a bounded analytical hop plan for the privacy-safe question. Each hop has
a concise sub-question, purpose, and dependency IDs. Do not emit SQL, URLs, code, credentials, or
chain-of-thought. Do not use forecasting. Return only the requested structured plan."""


class MultiHopPlanner:
    def __init__(self, llm_client: LLMClient, *, max_hops: int) -> None:
        if max_hops < 1:
            raise ValueError("Multi-hop maximum must be at least one")
        self._llm = llm_client
        self._max_hops = max_hops

    def create_plan(self, safe_question: str) -> MultiHopPlan:
        try:
            plan = self._llm.generate_structured(
                LLMRequest(
                    messages=[
                        LLMMessage(role=LLMRole.SYSTEM, content=_SYSTEM_PROMPT),
                        LLMMessage(role=LLMRole.USER, content=safe_question),
                    ],
                    temperature=0,
                ),
                MultiHopPlan,
            )
        except (LLMError, ValidationError) as exc:
            raise MultiHopPlanningError(
                "Multi-hop planning could not obtain valid structured output"
            ) from exc
        validate_multihop_plan(plan, max_hops=self._max_hops)
        return plan


def validate_multihop_plan(plan: MultiHopPlan, *, max_hops: int) -> tuple[HopPlan, ...]:
    if len(plan.hops) > max_hops:
        raise MultiHopPlanningError("Multi-hop plan exceeds the configured hop budget")
    by_id = {hop.hop_id: hop for hop in plan.hops}
    if len(by_id) != len(plan.hops):
        raise MultiHopPlanningError("Multi-hop plan IDs must be unique")
    for hop in plan.hops:
        if contains_disallowed_executable_content(hop.sub_question):
            raise MultiHopPlanningError(
                "Multi-hop sub-questions cannot contain executable code, SQL, or URLs"
            )
        if hop.hop_id in hop.depends_on:
            raise MultiHopPlanningError("A multi-hop step cannot depend on itself")
        if set(hop.depends_on) - set(by_id):
            raise MultiHopPlanningError("Multi-hop plan contains an unknown dependency")

    pending = list(plan.hops)
    ordered: list[HopPlan] = []
    resolved: set[str] = set()
    while pending:
        ready = [hop for hop in pending if set(hop.depends_on) <= resolved]
        if not ready:
            raise MultiHopPlanningError("Multi-hop dependency graph contains a cycle")
        for hop in ready:
            pending.remove(hop)
            ordered.append(hop)
            resolved.add(hop.hop_id)
    return tuple(ordered)
