"""Structural + integration tests for src/agent/graph.py.

These exist because of a real regression: commit 2975183 (Week 9, schema
guardrail) deleted the conditional edge from `fetch_mitre_context` to
`classify_with_llm` / `rf_fallback` and never replaced it. The graph still
compiled without error (LangGraph does not validate dead-end nodes at
compile time) and ran to completion, but silently stopped after
`fetch_mitre_context` -- no verdict was ever produced, and every caller
(evaluate.py, app.py, benchmark.py, run_agent.py) has a default fallback
that swallowed the missing result instead of raising. Nothing here should
be able to regress that silently again.
"""

from src.agent.graph import build_triage_graph


def _compiled_edges():
    graph = build_triage_graph()
    rep = graph.get_graph()
    return rep, {(edge.source, edge.target) for edge in rep.edges}


def test_every_non_end_node_has_an_outgoing_edge():
    """Catches any node that silently dead-ends instead of reaching END."""
    rep, edges = _compiled_edges()
    sources = {source for source, _ in edges}
    for name in rep.nodes:
        if name == "__end__":
            continue
        assert name in sources, f"node {name!r} has no outgoing edge -- it dead-ends the graph"


def test_fetch_mitre_context_routes_to_llm_and_rf_fallback():
    """Pins the exact edge that regressed: fetch_mitre_context must lead
    to both automated classification paths, not just sit there unrouted."""
    _, edges = _compiled_edges()
    assert ("fetch_mitre_context", "classify_with_llm") in edges
    assert ("fetch_mitre_context", "rf_fallback") in edges


def test_sparse_alert_produces_a_verdict_via_rf_fallback():
    """End-to-end integration check using the RF fallback path (no network
    call, no LLM, deterministic) -- a sparse alert must come out the other
    side of the graph with an actual predicted_label."""
    graph = build_triage_graph()
    sparse_alert = {
        "AlertTitle": 99999,
        "DetectorId": 5,
        "Category": "InitialAccess",
        # MitreTechniques / SuspicionLevel / LastVerdict all absent on
        # purpose -- this is what should_use_fallback() routes to RF.
    }
    result = graph.invoke({"raw_alert": sparse_alert})

    assert result.get("predicted_label") is not None, (
        "graph produced no verdict for a well-formed alert -- "
        "this is the exact failure mode of the fetch_mitre_context dead-end bug"
    )
    assert result.get("triage_path") == "rf_fallback"
