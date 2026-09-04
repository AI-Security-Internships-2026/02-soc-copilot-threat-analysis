# src/agent/graph.py
# wires all nodes into a LangGraph StateGraph.
#
# week 15 -- the pipeline's shape changed. Until now the graph chose between
# the LLM and the RF per alert, and whichever ran also decided the verdict.
# The control experiment in experiments/rf_vs_llm_control.py scored both models
# on the *same* 209 well-evidenced alerts and found the LLM at 0.2823 accuracy
# against the RF's 0.6555 -- below even the 0.4928 you get by always answering
# BenignPositive, on exactly the alerts that were supposed to be its strength.
# So the LLM no longer decides anything:
#
#   START -> regex_guardrail -> schema_guardrail -> fetch_mitre_context
#         -> build_context -> classify_with_rf -> explain_with_llm
#         -> (margin gate) -> END | human_review -> END
#
# Two ordering details in that chain matter:
#
#   1. fetch_mitre_context now runs BEFORE build_context. It used to run four
#      nodes later, so build_context's `if state.get("mitre_context")` branch
#      was always reading None and the ATT&CK enrichment never actually
#      reached the model. Under the new design the LLM's whole job is grounded
#      explanation, so that bug would have been much more damaging than it
#      already was.
#
#   2. explain_with_llm runs AFTER classify_with_rf, and cannot write
#      predicted_label. The verdict and the review decision are both settled
#      before any model-generated text exists, which is what makes prompt
#      injection an explanation-quality problem here rather than a triage
#      integrity one.
#
# The Weeks 6-14 hybrid graph is still buildable via mode="legacy_hybrid" so
# the comparison in the paper stays reproducible.
#
# A third mode, "llm_primary", was added for the control-node ablation: it
# sends every alert to the LLM unconditionally (no evidence-based routing),
# using the same corrected node order as rf_primary (fetch_mitre_context
# before build_context) rather than legacy_hybrid's order, so its numbers
# aren't confounded by the ordering bug described above. This is the only
# way to measure what the LLM does on evidence-poor alerts -- under both
# other modes it never sees them (rf_primary doesn't route by evidence at
# all; legacy_hybrid routes sparse alerts away from it).

from langgraph.graph import StateGraph, START, END

from src.agent.state import AlertState
from src.agent.nodes import (
    build_context,
    apply_regex_guardrail,
    apply_schema_guardrail,        # replaces apply_ml_guardrail
    route_after_schema_guardrail,  # replaces route_after_ml_guardrail
    fetch_mitre_context,
    classify_with_llm,
    classify_with_rf,              # week 15: sole writer of predicted_label
    explain_with_llm,              # week 15: rationale only, no label authority
    classify_with_fallback,
    parse_verdict,
    human_review_node,
    route_after_verdict,
    route_after_rf_verdict,        # week 15: gates on RF margin
    route_by_context,
    route_after_guardrail,
)


def _build_rf_primary_graph() -> StateGraph:
    """RF decides every verdict; the LLM explains it (week 15, current)."""
    graph = StateGraph(AlertState)

    graph.add_node("regex_guardrail", apply_regex_guardrail)
    graph.add_node("schema_guardrail", apply_schema_guardrail)
    graph.add_node("fetch_mitre_context", fetch_mitre_context)
    graph.add_node("build_context", build_context)
    graph.add_node("classify_with_rf", classify_with_rf)
    graph.add_node("explain_with_llm", explain_with_llm)
    graph.add_node("human_review", human_review_node)

    # Guardrails run first, before any alert text is used to build a prompt.
    graph.add_edge(START, "regex_guardrail")
    graph.add_conditional_edges(
        "regex_guardrail",
        route_after_guardrail,
        {"continue": "schema_guardrail", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "schema_guardrail",
        route_after_schema_guardrail,
        {"continue": "fetch_mitre_context", "human_review": "human_review"},
    )

    # Enrich, then build the context block so the enrichment is actually in it.
    graph.add_edge("fetch_mitre_context", "build_context")

    # Verdict, then explanation of that verdict.
    graph.add_edge("build_context", "classify_with_rf")
    graph.add_edge("classify_with_rf", "explain_with_llm")

    graph.add_conditional_edges(
        "explain_with_llm",
        route_after_rf_verdict,
        {"end": END, "human_review": "human_review"},
    )
    graph.add_edge("human_review", END)
    return graph


def _build_legacy_hybrid_graph() -> StateGraph:
    """The Weeks 6-14 pipeline, kept so published results stay reproducible.

    Retained for comparison only. This is the graph whose LLM branch scored
    0.2823 on the 209-alert control; do not use it to triage anything.
    """
    graph = StateGraph(AlertState)

    graph.add_node("build_context", build_context)
    graph.add_node("regex_guardrail", apply_regex_guardrail)
    graph.add_node("schema_guardrail", apply_schema_guardrail)
    graph.add_node("fetch_mitre_context", fetch_mitre_context)
    graph.add_node("classify_with_llm", classify_with_llm)
    graph.add_node("rf_fallback", classify_with_fallback)
    graph.add_node("parse_verdict", parse_verdict)
    graph.add_node("human_review", human_review_node)

    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "regex_guardrail")
    graph.add_conditional_edges(
        "regex_guardrail",
        route_after_guardrail,
        {"continue": "schema_guardrail", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "schema_guardrail",
        route_after_schema_guardrail,
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
    graph.add_conditional_edges(
        "parse_verdict",
        route_after_verdict,
        {"end": END, "human_review": "human_review"},
    )
    graph.add_edge("human_review", END)
    return graph


def _build_llm_primary_graph() -> StateGraph:
    """Every alert goes to the LLM, regardless of evidence density.

    Ablation-only mode: measures what the LLM does on the alerts rf_primary
    and legacy_hybrid never let it see (evidence-poor ones). Do not use to
    triage anything -- the 209-alert control already showed the LLM losing
    to a majority-class guess on the alerts *most* favourable to it.
    """
    graph = StateGraph(AlertState)

    graph.add_node("regex_guardrail", apply_regex_guardrail)
    graph.add_node("schema_guardrail", apply_schema_guardrail)
    graph.add_node("fetch_mitre_context", fetch_mitre_context)
    graph.add_node("build_context", build_context)
    graph.add_node("classify_with_llm", classify_with_llm)
    graph.add_node("parse_verdict", parse_verdict)
    graph.add_node("human_review", human_review_node)

    graph.add_edge(START, "regex_guardrail")
    graph.add_conditional_edges(
        "regex_guardrail",
        route_after_guardrail,
        {"continue": "schema_guardrail", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "schema_guardrail",
        route_after_schema_guardrail,
        {"continue": "fetch_mitre_context", "human_review": "human_review"},
    )
    graph.add_edge("fetch_mitre_context", "build_context")
    graph.add_edge("build_context", "classify_with_llm")
    graph.add_edge("classify_with_llm", "parse_verdict")
    graph.add_conditional_edges(
        "parse_verdict",
        route_after_verdict,
        {"end": END, "human_review": "human_review"},
    )
    graph.add_edge("human_review", END)
    return graph


def build_triage_graph(mode: str = "rf_primary"):
    """
    builds and compiles the triage agent graph.
    returns a compiled graph that can be invoked like a function:
        result = graph.invoke({"raw_alert": {...}})

    mode:
      "rf_primary"    -- current design: RF decides, LLM explains (week 15)
      "legacy_hybrid" -- Weeks 6-14 design, for reproducing published results
      "llm_primary"   -- ablation-only: LLM decides every alert unconditionally
    """
    if mode == "rf_primary":
        graph = _build_rf_primary_graph()
    elif mode == "legacy_hybrid":
        graph = _build_legacy_hybrid_graph()
    elif mode == "llm_primary":
        graph = _build_llm_primary_graph()
    else:
        raise ValueError(
            f"unknown graph mode {mode!r}; expected 'rf_primary', 'legacy_hybrid', "
            "or 'llm_primary'"
        )
    # compile locks the graph structure and prepares it for invocation
    return graph.compile()


# build the graph at import time so it's ready to use
triage_graph = build_triage_graph()
