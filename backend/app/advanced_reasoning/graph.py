"""LangGraph topology for bounded generic advanced reasoning."""

from typing import Protocol

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.advanced_reasoning.state import AdvancedReasoningState

ADVANCED_REASONING_NODE_SEQUENCE = (
    "decompose",
    "plan_tools",
    "execute",
    "reflect",
    "synthesize",
)


class AdvancedReasoningGraphNodes(Protocol):
    max_replans: int

    def decompose(self, state: AdvancedReasoningState) -> AdvancedReasoningState: ...

    def plan_tools(self, state: AdvancedReasoningState) -> AdvancedReasoningState: ...

    def execute(self, state: AdvancedReasoningState) -> AdvancedReasoningState: ...

    def reflect(self, state: AdvancedReasoningState) -> AdvancedReasoningState: ...

    def synthesize(self, state: AdvancedReasoningState) -> AdvancedReasoningState: ...

    def should_replan(self, state: AdvancedReasoningState) -> bool: ...


def build_advanced_reasoning_graph(nodes: AdvancedReasoningGraphNodes) -> CompiledStateGraph:
    builder = StateGraph(AdvancedReasoningState)
    builder.add_node("decompose", nodes.decompose)
    builder.add_node("plan_tools", nodes.plan_tools)
    builder.add_node("execute", nodes.execute)
    builder.add_node("reflect", nodes.reflect)
    builder.add_node("synthesize", nodes.synthesize)
    builder.add_edge(START, "decompose")
    builder.add_edge("decompose", "plan_tools")
    builder.add_edge("plan_tools", "execute")
    builder.add_edge("execute", "reflect")
    builder.add_conditional_edges(
        "reflect",
        lambda state: "replan" if nodes.should_replan(state) else "synthesize",
        {"replan": "plan_tools", "synthesize": "synthesize"},
    )
    builder.add_edge("synthesize", END)
    return builder.compile(name="advanced_reasoning")
