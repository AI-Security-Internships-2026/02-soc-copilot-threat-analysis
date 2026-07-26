# src/agent/graph.py
# wires all nodes into a LangGraph StateGraph.
# the graph defines the order of execution:
#   START → build_context → fetch_mitre_context → (LLM | RF fallback) → verdict → (conditional) → END
# each node updates the shared AlertState and passes it to the next.
# week 4: added fetch_mitre_context node and a conditional human-review checkpoint
# after parse_verdict — alerts with confidence != "high" get routed to human_review
# before ending, instead of going straight to END.

from langgraph.graph import StateGraph, START, END

from src.agent.state import AlertState
from src.agent.nodes import (
    build_context,
    apply_regex_guardrail,
    fetch_mitre_context,
    classify_with_llm,
    classify_with_fallback,
    parse_verdict,
    human_review_node,
    route_after_verdict,
    route_by_context,
    route_after_guardrail,
)


def build_triage_graph():
    """
    builds and compiles the triage agent graph.
    returns a compiled graph that can be invoked like a function:
        result = graph.invoke({"raw_alert": {...}})
    """
    # create the graph with AlertState as the shared state type
    graph = StateGraph(AlertState)

    # register each node — the string name is how langgraph refers to it
    graph.add_node("build_context", build_context)
    graph.add_node("regex_guardrail", apply_regex_guardrail)
    graph.add_node("fetch_mitre_context", fetch_mitre_context)   # week 4
    graph.add_node("classify_with_llm", classify_with_llm)
    graph.add_node("rf_fallback", classify_with_fallback)       # week 6
    graph.add_node("parse_verdict", parse_verdict)
    graph.add_node("human_review", human_review_node)            # week 4

    # define edges — the execution order
    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "regex_guardrail")
    graph.add_conditional_edges(
        "regex_guardrail",
        route_after_guardrail,
        {"continue": "fetch_mitre_context", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "fetch_mitre_context",
        route_by_context,
        {"llm": "classify_with_llm", "rf_fallback": "rf_fallback"},
    )
    graph.add_edge("classify_with_llm", "parse_verdict")
    graph.add_conditional_edges(
        "rf_fallback",
        route_after_verdict,
        {"end": END, "human_review": "human_review"},
    )

    # week 4: conditional checkpoint — high confidence goes straight to END,
    # anything else (medium/low) gets flagged for human review first
    graph.add_conditional_edges(
        "parse_verdict",
        route_after_verdict,
        {
            "end": END,
            "human_review": "human_review",
        },
    )
    graph.add_edge("human_review", END)

    # compile locks the graph structure and prepares it for invocation
    return graph.compile()


# build the graph at import time so it's ready to use
triage_graph = build_triage_graph()
