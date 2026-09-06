# src/agent/state.py
# defines the shared "state" object that flows through the LangGraph pipeline.
# every node reads from this and writes updates back into it.
# think of it like a shared notepad that gets passed between steps.

from typing import TypedDict, Optional, Dict, Any


class AlertState(TypedDict):
    raw_alert: Dict[str, Any]           # input
    alert_context: Optional[str]        # after build_context
    mitre_context: Optional[str]        # after fetch_mitre_context
    llm_response: Optional[str]         # after explain_with_llm (raw model output)
    predicted_label: Optional[str]      # set ONLY by classify_with_rf (week 15)
    reasoning: Optional[str]
    rationale: Optional[str]            # analyst-facing explanation from the LLM
    rationale_status: Optional[str]     # "generated" | "unavailable"
    confidence: Optional[str]           # "high" | "medium" | "low"
    triage_path: Optional[str]          # "rf_primary" | "llm" | "rf_fallback"
    context_signal_count: Optional[int] # populated MITRE/suspicion/verdict fields
    fallback_probability: Optional[float]
    rf_margin: Optional[float]          # top-1 minus top-2 probability (week 15)
    guardrail_status: Optional[str]    # "passed" | "blocked"
    guardrail_reasons: Optional[list[str]]
    needs_human_review: Optional[bool]  # after human_review_node
    error: Optional[str]
    ml_guardrail_status: Optional[str]   # "passed" | "blocked"
    ml_guardrail_reasons: Optional[list[str]]
    schema_guardrail_status: Optional[str]   # "passed" | "blocked"
    schema_guardrail_reasons: Optional[list[str]]