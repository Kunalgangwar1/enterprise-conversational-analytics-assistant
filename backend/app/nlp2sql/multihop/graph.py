"""Bounded LangGraph topology for multi-hop SQL analysis."""

from typing import Protocol

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.nlp2sql.multihop.state import MultiHopState

MULTIHOP_NODE_SEQUENCE = (
    "plan",
    "execute_hop",
    "check_budget_and_remaining",
    "prepare_next_hop",
    "synthesize",
)


class MultiHopGraphNodes(Protocol):
    def plan(self, state: MultiHopState) -> MultiHopState: ...

    def execute_hop(self, state: MultiHopState) -> MultiHopState: ...

    def check_budget_and_remaining(self, state: MultiHopState) -> MultiHopState: ...

    def prepare_next_hop(self, state: MultiHopState) -> MultiHopState: ...

    def synthesize(self, state: MultiHopState) -> MultiHopState: ...


def build_multihop_graph(nodes: MultiHopGraphNodes) -> CompiledStateGraph:
    builder = StateGraph(MultiHopState)
    builder.add_node("plan", nodes.plan)
    builder.add_node("execute_hop", nodes.execute_hop)
    builder.add_node("check_budget_and_remaining", nodes.check_budget_and_remaining)
    builder.add_node("prepare_next_hop", nodes.prepare_next_hop)
    builder.add_node("synthesize", nodes.synthesize)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", "execute_hop")
    builder.add_edge("execute_hop", "check_budget_and_remaining")
    builder.add_conditional_edges(
        "check_budget_and_remaining",
        lambda state: (
            "more" if state["current_hop_index"] < len(state["ordered_hops"]) else "complete"
        ),
        {"more": "prepare_next_hop", "complete": "synthesize"},
    )
    builder.add_edge("prepare_next_hop", "execute_hop")
    builder.add_edge("synthesize", END)
    return builder.compile(name="multihop_nlp2sql")
