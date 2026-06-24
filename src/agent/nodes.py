# src/agent/nodes.py
# each function here is one "node" in the LangGraph pipeline.
# a node takes the current state, does something, and returns a dict of updates.
# langgraph merges those updates back into the state automatically.

import os
import json
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.state import AlertState

load_dotenv()  # loads OPENAI_API_KEY from .env file

# initialise the LLM once at module level so it's reused across calls
# gpt-4o-mini is cheap and fast — good for triage tasks
llm = ChatGroq(
    model="llama-3.1-8b-instant",   # free, fast, good at structured output
    temperature=0,
    max_tokens=512,
)


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

    return {"alert_context": alert_context}


# ---------------------------------------------------------------------------
# node 2: llm_classifier
# ---------------------------------------------------------------------------
def classify_with_llm(state: AlertState) -> dict:
    """
    sends the alert context to the LLM with a structured prompt.
    asks for a verdict (TruePositive / BenignPositive / FalsePositive),
    a confidence level, and a short reasoning.
    the LLM is instructed to respond in JSON so we can parse it reliably.
    """
    if state.get("error"):
        # skip if a previous node already errored
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

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])
        return {"llm_response": response.content}

    except Exception as e:
        return {"error": f"LLM call failed: {str(e)}"}


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