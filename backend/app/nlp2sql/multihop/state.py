"""Typed LangGraph state for multi-hop SQL execution."""

from collections.abc import Sequence
from typing import TypedDict

from app.nlp2sql.multihop.budget import MultiHopBudget
from app.nlp2sql.multihop.models import HopPlan, HopResult, MultiHopPlan, MultiHopSynthesis
from app.privacy.models import TokenMappingEntry


class MultiHopState(TypedDict, total=False):
    safe_question: str
    token_mappings: Sequence[TokenMappingEntry]
    plan: MultiHopPlan
    ordered_hops: tuple[HopPlan, ...]
    current_hop_index: int
    hop_results: tuple[HopResult, ...]
    budget: MultiHopBudget
    synthesis: MultiHopSynthesis
    answer_markdown: str
