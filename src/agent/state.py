# src/agent/state.py
# defines the shared "state" object that flows through the LangGraph pipeline.
# every node reads from this and writes updates back into it.
# think of it like a shared notepad that gets passed between steps.

from typing import TypedDict, Optional, Dict, Any


class AlertState(TypedDict):
    # --- input ---
    # the raw alert as a dictionary of feature name → value
    # e.g. {"AlertTitle": "Suspicious Login", "Category": "Credential Access", ...}
    raw_alert: Dict[str, Any]

    # --- built by context_builder node ---
    # a clean human-readable string summary of the alert, passed to the LLM
    alert_context: Optional[str]

    # --- filled in by llm_classifier node ---
    # the raw text response from the LLM
    llm_response: Optional[str]

    # --- filled in by verdict_parser node ---
    # the final parsed prediction: "TruePositive", "BenignPositive", or "FalsePositive"
    predicted_label: Optional[str]

    # the LLM's explanation of why it gave this verdict
    reasoning: Optional[str]

    # confidence: "high", "medium", or "low" — extracted from LLM response
    confidence: Optional[str]

    # any error that happened during processing — used to skip to END gracefully
    error: Optional[str]