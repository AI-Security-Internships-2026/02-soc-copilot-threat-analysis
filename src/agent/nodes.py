# src/agent/nodes.py
# each function here is one "node" in the LangGraph pipeline.
# a node takes the current state, does something, and returns a dict of updates.
# langgraph merges those updates back into the state automatically.

import os
import json
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import re
import time

from src.agent.state import AlertState
from src.agent.fallback_classifier import (
    evidence_field_count,
    predict_with_fallback,
    should_use_fallback,
)
from src.agent.guardrails import inspect_alert

# add this import near your other imports at the top of nodes.py
from src.agent.mitre_lookup import get_technique_info, load_technique_map

# load once at module level so it's not re-reading the cache file on every alert
_MITRE_TECHNIQUE_MAP = None

load_dotenv()  # loads OPENAI_API_KEY from .env file

# initialise the LLM once at module level so it's reused across calls
# gpt-4o-mini is cheap and fast — good for triage tasks
llm = ChatGroq(
    model="llama-3.1-8b-instant",   # free, fast, good at structured output
    temperature=0,
    max_tokens=512,
)

llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    max_tokens=512,
)

MAX_LLM_RETRIES = 5


def _extract_retry_seconds(error_message: str, default: float = 2.0) -> float:
    """Parse Groq's 'Please try again in X.Xs' out of its own error message
    instead of guessing a backoff — Groq already tells us the exact wait."""
    match = re.search(r"try again in ([\d.]+)s", error_message)
    if match:
        return float(match.group(1)) + 0.25  # small safety buffer
    return default

# ---------------------------------------------------------------------------
# node 1: context_builder
# ---------------------------------------------------------------------------
def build_context(state: AlertState) -> dict:
    """
    converts the raw alert dict into a clean, readable text block.
    this is what gets sent to the LLM — structured but human-readable.
    """
    alert = state["raw_alert"]

    # pull out the most meaningful fields for the LLM to reason about.
    # we skip raw IDs (OrgId, AlertId, etc.) — they don't help reasoning.
    context_parts = []

    if alert.get("AlertTitle"):
        context_parts.append(f"Alert Title: {alert['AlertTitle']}")

    if alert.get("Category"):
        context_parts.append(f"Category: {alert['Category']}")

    if alert.get("MitreTechniques"):
        context_parts.append(f"MITRE Technique: {alert['MitreTechniques']}")

    if alert.get("DetectorId"):
        context_parts.append(f"Detector: {alert['DetectorId']}")

    if alert.get("Hour") is not None:
        context_parts.append(f"Hour of Day: {alert['Hour']}")

    if alert.get("DayOfWeek") is not None:
        context_parts.append(f"Day of Week (0=Mon): {alert['DayOfWeek']}")

    if alert.get("SuspicionLevel"):
        context_parts.append(f"Suspicion Level: {alert['SuspicionLevel']}")

    if alert.get("LastVerdict"):
        context_parts.append(f"Last Verdict: {alert['LastVerdict']}")

    # join into a clean block
    alert_context = "\n".join(context_parts) if context_parts else "No alert details available."
    
    if state.get("mitre_context"):
        alert_context += f"\n\nMITRE ATT&CK context: {state['mitre_context']}"

    return {"alert_context": alert_context}


# ---------------------------------------------------------------------------
# input guardrail
# ---------------------------------------------------------------------------
def apply_regex_guardrail(state: AlertState) -> dict:
    """Block prompt-injection-like alert text before it can reach the LLM."""
    reasons = inspect_alert(state["raw_alert"])
    if not reasons:
        return {"guardrail_status": "passed", "guardrail_reasons": []}
    return {
        "guardrail_status": "blocked",
        "guardrail_reasons": reasons,
        "confidence": "low",
        "needs_human_review": True,
        "reasoning": "Input regex guardrail blocked LLM processing: " + ", ".join(reasons),
    }


def route_after_guardrail(state: AlertState) -> str:
    """Keep blocked text out of both LLM and automated RF disposition paths."""
    return "human_review" if state.get("guardrail_status") == "blocked" else "continue"


# ---------------------------------------------------------------------------
# node 2: llm_classifier
# ---------------------------------------------------------------------------
def classify_with_llm(state: AlertState) -> dict:
    """
    sends the alert context to the LLM with a structured prompt.
    asks for a verdict (TruePositive / BenignPositive / FalsePositive),
    a confidence level, and a short reasoning.
    the LLM is instructed to respond in JSON so we can parse it reliably.

    retries on Groq 429 rate-limit errors using the wait time Groq itself
    returns, instead of failing immediately. non-rate-limit errors are not
    retried.
    """
    if state.get("error"):
        return {}

    system_prompt = """You are a senior SOC analyst. Your job is to triage cybersecurity alerts.

Given an alert, classify it as one of:
- TruePositive: a real attack or malicious activity
- BenignPositive: a real event but not malicious (e.g. admin activity, false alarm from legit use)
- FalsePositive: the alert fired incorrectly, no real event occurred

Respond ONLY with a JSON object in this exact format, no extra text:
{
  "verdict": "TruePositive" | "BenignPositive" | "FalsePositive",
  "confidence": "high" | "medium" | "low",
  "reasoning": "one or two sentences explaining your verdict"
}"""

    user_message = f"Triage this alert:\n\n{state['alert_context']}"
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    last_error = None
    for attempt in range(MAX_LLM_RETRIES):
        try:
            response = llm.invoke(messages)
            return {"llm_response": response.content, "triage_path": "llm"}
        except Exception as e:
            last_error = str(e)
            if "rate_limit_exceeded" in last_error or "429" in last_error:
                wait_seconds = _extract_retry_seconds(last_error)
                time.sleep(wait_seconds)
                continue
            break  # non-rate-limit error: don't retry, fail immediately

    return {"error": f"LLM call failed after {MAX_LLM_RETRIES} attempts: {last_error}", "triage_path": "llm_error"}

# ---------------------------------------------------------------------------
# week 6: low-context fallback classifier
# ---------------------------------------------------------------------------
def route_by_context(state: AlertState) -> str:
    """Route sparse GUIDE alerts to RF; retain the LLM path otherwise."""
    alert = state["raw_alert"]
    return "rf_fallback" if should_use_fallback(alert) else "llm"


def classify_with_fallback(state: AlertState) -> dict:
    """Classify a sparse alert with the structured-data RF baseline.

    The fallback is deliberately narrow. If its model cannot run, return a
    low-confidence result for human review instead of silently guessing.
    """
    signal_count = evidence_field_count(state["raw_alert"])
    try:
        label, probability = predict_with_fallback(state["raw_alert"])
    except Exception as exc:
        return {
            "confidence": "low",
            "triage_path": "rf_fallback",
            "context_signal_count": signal_count,
            "reasoning": f"RF fallback unavailable; requires human review: {exc}",
            "error": f"RF fallback failed: {exc}",
        }

    confidence = "high" if probability >= 0.80 else "medium" if probability >= 0.55 else "low"
    return {
        "predicted_label": label,
        "confidence": confidence,
        "triage_path": "rf_fallback",
        "context_signal_count": signal_count,
        "fallback_probability": probability,
        "reasoning": (
            f"RF fallback used because only {signal_count}/{len(('MitreTechniques', 'SuspicionLevel', 'LastVerdict'))} "
            f"discriminative context fields were populated (model probability: {probability:.2f})."
        ),
    }


# ---------------------------------------------------------------------------
# node 3: verdict_parser
# ---------------------------------------------------------------------------
def parse_verdict(state: AlertState) -> dict:
    """
    parses the LLM's JSON response into structured fields.
    if parsing fails, falls back to "FalsePositive" with low confidence
    so the pipeline never crashes — it just flags the uncertainty.
    """
    if state.get("error"):
        return {}

    raw = state.get("llm_response", "")

    try:
        # strip any accidental markdown fences the LLM might add
        clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
        parsed = json.loads(clean)

        verdict = parsed.get("verdict", "FalsePositive")
        confidence = parsed.get("confidence", "low")
        reasoning = parsed.get("reasoning", "No reasoning provided.")

        # normalise verdict spelling just in case
        valid_verdicts = {"TruePositive", "BenignPositive", "FalsePositive"}
        if verdict not in valid_verdicts:
            verdict = "FalsePositive"
            confidence = "low"
            reasoning = f"Could not parse verdict. Raw response: {raw}"

        return {
            "predicted_label": verdict,
            "confidence": confidence,
            "reasoning": reasoning,
        }

    except (json.JSONDecodeError, AttributeError) as e:
        return {
            "predicted_label": "FalsePositive",
            "confidence": "low",
            "reasoning": f"Parse error: {str(e)}. Raw: {raw}",
        }
        

def fetch_mitre_context(state: AlertState) -> AlertState:
    """
    week 4 node: looks up MITRE ATT&CK technique info if the alert has a
    MitreTechniques field, and adds it to state so it can be injected into
    the LLM prompt in classify_with_llm.
    """
    global _MITRE_TECHNIQUE_MAP
    if _MITRE_TECHNIQUE_MAP is None:
        _MITRE_TECHNIQUE_MAP = load_technique_map()

    technique_id = state["raw_alert"].get("MitreTechniques", "")
    mitre_info = get_technique_info(technique_id, _MITRE_TECHNIQUE_MAP)

    if mitre_info:
        state["mitre_context"] = mitre_info
    else:
        state["mitre_context"] = "no MITRE ATT&CK technique info available for this alert"

    return state


def human_review_node(state: AlertState) -> AlertState:
    """
    week 4 node: checkpoint that fires when the LLM's confidence is
    medium or low. doesn't actually block on a human, just flags the
    alert so a human can review it later instead of auto-triaging it.
    """
    state["needs_human_review"] = True
    state["reasoning"] = (state.get("reasoning") or "") + \
        " [flagged for human review: confidence was not high]"
    return state


def route_after_verdict(state: AlertState) -> str:
    """
    conditional edge function: decides where to go after parse_verdict.
    returns the name of the next node as a string, which graph.py uses
    to wire up the conditional edge.
    """
    if state.get("confidence") == "high":
        return "end"
    return "human_review"
