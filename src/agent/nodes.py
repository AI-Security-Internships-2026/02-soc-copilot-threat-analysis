# src/agent/nodes.py
# each function here is one "node" in the LangGraph pipeline.
# a node takes the current state, does something, and returns a dict of updates.
# langgraph merges those updates back into the state automatically.

import os
import json
import pandas as pd
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
import re
import time
from src.agent.state import AlertState
from src.agent.fallback_classifier import (
    EVIDENCE_FIELDS,
    evidence_field_count,
    predict_with_fallback,
    predict_with_margin,
    should_use_fallback,
)
from src.agent.guardrails import inspect_alert
from src.agent.mitre_lookup import get_technique_info, load_technique_map
from src.agent.schema_guardrail import validate_field_types

# load once at module level so it's not re-reading the cache file on every alert
_MITRE_TECHNIQUE_MAP = None

load_dotenv()  # loads GROQ_API_KEY from .env file

# initialise the LLM once at module level so it's reused across calls
# llama-3.1-8b-instant was retired from Groq's catalog (confirmed via a live
# 404 + client.models.list() while wiring up Week 11's deepteam eval, which
# calls this same node) -- replaced with openai/gpt-oss-20b, a reasoning
# model, hence the higher max_tokens to leave room for its hidden reasoning
# tokens ahead of the actual JSON answer.
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    max_tokens=1024,
)

MAX_LLM_RETRIES = 5


def _extract_retry_seconds(error_message: str, default: float = 2.0) -> float:
    """Parse Groq's 'Please try again in X.Xs' out of its own error message
    instead of guessing a backoff — Groq already tells us the exact wait."""
    match = re.search(r"try again in ([\d.]+)s", error_message)
    if match:
        return float(match.group(1)) + 0.25  # small safety buffer
    return default

def _has_value(value) -> bool:
    """True if `value` is a real, present value -- unlike a bare truthiness
    check, this correctly treats a missing-data NaN float as absent instead
    of truthy. Week 12 finding: GUIDE alerts loaded via pandas represent
    missing MitreTechniques/SuspicionLevel/etc. as float('nan'), and
    bool(float('nan')) is True in Python -- so the old `if alert.get(field):`
    checks below were literally sending the LLM a "MITRE Technique: nan" /
    "Suspicion Level: nan" line on every alert where that field was actually
    missing (55% and 31% of LLM-routed alerts respectively, see
    experiments/llm_subset_eval.py). Mirrors
    src/agent/fallback_classifier.py's _present()."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    try:
        return not pd.isna(value)
    except (TypeError, ValueError):
        return True


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

    if _has_value(alert.get("AlertTitle")):
        context_parts.append(f"Alert Title: {alert['AlertTitle']}")

    if _has_value(alert.get("Category")):
        context_parts.append(f"Category: {alert['Category']}")

    if _has_value(alert.get("MitreTechniques")):
        context_parts.append(f"MITRE Technique: {alert['MitreTechniques']}")

    if _has_value(alert.get("DetectorId")):
        context_parts.append(f"Detector: {alert['DetectorId']}")

    if alert.get("Hour") is not None:
        context_parts.append(f"Hour of Day: {alert['Hour']}")

    if alert.get("DayOfWeek") is not None:
        context_parts.append(f"Day of Week (0=Mon): {alert['DayOfWeek']}")

    if _has_value(alert.get("SuspicionLevel")):
        context_parts.append(f"Suspicion Level: {alert['SuspicionLevel']}")

    if _has_value(alert.get("LastVerdict")):
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
# Note on the removed ML guardrail (issue #10, Weeks 8-9).
#
# A TF-IDF + logistic-regression injection detector used to sit here as a
# second guardrail stage. It was never wired into the compiled graph after
# Week 9 -- experiments/soc_domain_eval.py measured it at 0.525 accuracy with
# 0.05 recall on the project's own 40-example set, i.e. no better than chance
# at the thresholds that would have been safe to gate on. It was replaced by
# the deterministic schema check below, which catches the same class of
# malformed input by construction rather than by a learned score.
#
# Week 15 deleted the dead node and its import. The scoring module
# (src/agent/ml_guardrail.py) and its evaluation are deliberately kept: the
# negative result is a documented finding, not dead weight.
# ---------------------------------------------------------------------------
# input guardrail, stage 2 replacement: deterministic schema/type check
# (issue #10, week 9 -- replaces the ml classifier, see schema_guardrail.py)
# ---------------------------------------------------------------------------
def apply_schema_guardrail(state: AlertState) -> dict:
    """second-stage check: fields that must be numeric IDs actually are."""
    reasons = validate_field_types(state["raw_alert"])
    if not reasons:
        return {"schema_guardrail_status": "passed"}

    return {
        "schema_guardrail_status": "blocked",
        "schema_guardrail_reasons": reasons,
        "confidence": "low",
        "needs_human_review": True,
        "reasoning": "Schema guardrail flagged non-numeric ID field: " + ", ".join(reasons),
    }


def route_after_schema_guardrail(state: AlertState) -> str:
    return "human_review" if state.get("schema_guardrail_status") == "blocked" else "continue"


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

    # Week 12 tested this against the original prompt above (kept in
    # experiments/llm_subset_eval.py as BASELINE_SYSTEM_PROMPT) and found it
    # both more accurate (macro F1 0.268 vs 0.151 on the same 60-alert subset)
    # and, per a Week 14 reasoning-groundedness content analysis, less
    # templated: reasoning text referencing specific alert evidence (a MITRE
    # technique, a named Suspicion Level/Last Verdict) rose from 15% to 47% of
    # cases, generic boilerplate phrasing ("no evidence of malicious
    # activity") dropped from 55% to 0%, and specificity started correlating
    # with correctness (60% on correct verdicts vs 40% on incorrect, versus
    # no meaningful gap under the old prompt) -- see docs/weekly-progress.md.
    system_prompt = """You are a senior SOC analyst triaging alerts from the Microsoft GUIDE \
telemetry pipeline. Alert titles and category codes are often just numeric IDs, not human-readable \
descriptions -- that is normal for this data, not missing information.

Classify each alert as one of:
- TruePositive: a real attack or malicious activity actually occurred
- BenignPositive: a real event occurred but it was not malicious (e.g. legitimate admin activity,
  a security control correctly firing on non-malicious behavior)
- FalsePositive: the alert fired incorrectly and no real event of the described kind occurred

The strongest signals, when present, are:
- "Last Verdict": an existing system/analyst judgement on this exact evidence (e.g. "Malicious",
  "Suspicious", "NoThreatsFound"). Treat it as strong prior evidence, not decisive on its own --
  "Suspicious" does not always mean TruePositive, and "NoThreatsFound" does not always mean
  FalsePositive rather than BenignPositive.
- "Suspicion Level": a system-assigned risk rating for this alert.
- "MITRE Technique": a specific attacker technique ID is stronger evidence of real attack activity
  than a Category alone.
A numeric-only Alert Title or Category with no MITRE technique or verdict signal is weak evidence
either way -- do not treat the mere presence of a Category like "InitialAccess" as proof of an
attack; many benign/false-positive alerts also carry attack-stage categories because that is how
the detector that fired is classified, not because an attack occurred.

Examples (illustrative, not exhaustive):
- Alert Title: 15723 | Category: Collection | Suspicion Level: Suspicious | Last Verdict: Suspicious
  -> TruePositive: category, suspicion level, and last verdict all independently point toward real
  malicious activity, even though the alert title itself is just a numeric code.
- Alert Title: 4 | Category: SuspiciousActivity | Suspicion Level: Suspicious | Last Verdict: NoThreatsFound
  -> BenignPositive: the detector flagged something real (Suspicious category/level), but the
  system's own last verdict already concluded no actual threat was found -- a real but non-malicious
  event, not a misfire.
- Alert Title: 0 | Category: InitialAccess | MITRE Technique: none listed | no Suspicion Level or Last Verdict
  -> FalsePositive: a bare numeric title and category with no technique ID and no corroborating
  verdict/suspicion signal is exactly the pattern of a detector misfire, not a real event.

Respond ONLY with a JSON object in this exact format, no extra text:
{
  "reasoning": "one or two sentences citing the specific fields that drove your verdict",
  "verdict": "TruePositive" | "BenignPositive" | "FalsePositive",
  "confidence": "high" | "medium" | "low"
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
            f"RF fallback used because only {signal_count}/{len(EVIDENCE_FIELDS)} "
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
    week 4 node: checkpoint that flags an alert for a human instead of
    auto-triaging it. doesn't actually block on a human.

    week 15: the reason is now recorded accurately. This node is reached for
    three quite different situations -- a guardrail block, an outright
    failure, and a genuine low-confidence verdict -- and previously labelled
    all three "confidence was not high", which turned an API outage into what
    looked like an ordinary uncertain call in the logs.
    """
    state["needs_human_review"] = True

    if state.get("error"):
        reason = f"flagged for human review: no automated verdict ({state['error']})"
    elif state.get("guardrail_status") == "blocked":
        reason = "flagged for human review: input guardrail blocked this alert"
    elif state.get("schema_guardrail_status") == "blocked":
        reason = "flagged for human review: alert failed schema validation"
    elif state.get("rf_margin") is not None:
        reason = (
            f"flagged for human review: RF decision margin "
            f"{state['rf_margin']:.2f} is below the {RF_REVIEW_MARGIN_THRESHOLD:.2f} "
            f"threshold, so this verdict is not safe to auto-action"
        )
    else:
        reason = "flagged for human review: confidence was not high"

    state["reasoning"] = f"{(state.get('reasoning') or '').strip()} [{reason}]".strip()
    return state


def route_after_verdict(state: AlertState) -> str:
    """
    conditional edge function: decides where to go after parse_verdict.
    returns the name of the next node as a string, which graph.py uses
    to wire up the conditional edge.

    Used by the legacy hybrid graph only. The rf_primary graph gates on
    route_after_rf_verdict below, because this function trusts a
    self-reported confidence string that Week 15 measured as inverted.
    """
    if state.get("confidence") == "high":
        return "end"
    return "human_review"


# ---------------------------------------------------------------------------
# week 15: RF decides, LLM explains
#
# Week 15's control experiment (experiments/rf_vs_llm_control.py) scored the RF
# and the LLM on the *same* 209 well-evidenced alerts, eliminating the confound
# that had made every previous comparison unreadable -- until then the two
# models had only ever been measured on different alerts, so the LLM's lower
# score could have meant its alerts were harder. They were not:
#
#     RandomForest   accuracy 0.6555   macro F1 0.6035
#     LLM            accuracy 0.2823   macro F1 0.2121
#     majority-class floor            0.4928
#
# The LLM scored below "always answer BenignPositive" on the alerts chosen as
# its best case, and lost 105 of the 132 disagreements (McNemar p = 4.7e-12).
#
# The nodes below implement the consequence. The RF classifies every alert and
# is the only writer of predicted_label. The LLM keeps the job it is actually
# good at -- turning structured evidence into an explanation an analyst can
# read -- and is structurally prevented from influencing the verdict.
# ---------------------------------------------------------------------------

# Chosen from the margin sweep in experiments/results/rf_vs_llm_control.json
# rather than by feel. At 0.20 the auto-accepted alerts score 0.6905 (up from
# 0.6555 ungated) while 19.6% of alerts go to a human -- roughly one in five,
# which is affordable review load. The next step up (0.30) buys only another
# 2 accuracy points but escalates 35.4%, which is not.
RF_REVIEW_MARGIN_THRESHOLD = 0.20


def classify_with_rf(state: AlertState) -> dict:
    """Assign the verdict with the Random Forest. The only writer of a label.

    Confidence is derived from the RF's decision margin (top-1 minus top-2
    probability), which Week 15 verified is monotonically related to accuracy,
    unlike the LLM's self-reported confidence.
    """
    signal_count = evidence_field_count(state["raw_alert"])
    try:
        label, probability, margin = predict_with_margin(state["raw_alert"])
    except Exception as exc:
        # Surface the failure rather than guessing a class. A fabricated label
        # here would be indistinguishable from a real prediction downstream.
        return {
            "confidence": "low",
            "triage_path": "rf_primary",
            "context_signal_count": signal_count,
            "reasoning": f"RF classifier unavailable; requires human review: {exc}",
            "error": f"RF classifier failed: {exc}",
        }

    confidence = "high" if margin >= RF_REVIEW_MARGIN_THRESHOLD else "low"
    return {
        "predicted_label": label,
        "confidence": confidence,
        "triage_path": "rf_primary",
        "context_signal_count": signal_count,
        "fallback_probability": probability,
        "rf_margin": margin,
        "reasoning": (
            f"Random Forest verdict {label} (probability {probability:.2f}, "
            f"decision margin {margin:.2f} against a review threshold of "
            f"{RF_REVIEW_MARGIN_THRESHOLD:.2f}); {signal_count}/"
            f"{len(EVIDENCE_FIELDS)} discriminative context fields populated."
        ),
    }


def explain_with_llm(state: AlertState) -> dict:
    """Write an analyst-facing explanation of a verdict the RF already made.

    This node deliberately cannot change the outcome. It never returns
    predicted_label or confidence, so a wrong, malicious, or injected LLM
    response degrades the explanation and nothing else -- the verdict, the
    review decision, and every metric are already fixed before it runs.

    A failure here is not a triage failure: the alert keeps its verdict and is
    simply shown without a natural-language rationale.

    Set SOC_COPILOT_SKIP_EXPLANATION=1 to skip the call entirely. Because the
    explanation cannot affect the verdict, the review decision, or any metric,
    accuracy evaluation over thousands of alerts is exactly identical with it
    off -- and runs offline, deterministically, and without consuming API
    quota. That equivalence is a property of the architecture, not a shortcut:
    under the pre-Week-15 design, skipping the LLM would have changed the
    results, which is the point.
    """
    if os.getenv("SOC_COPILOT_SKIP_EXPLANATION") == "1":
        return {"rationale": None, "rationale_status": "skipped"}

    if state.get("error") or not state.get("predicted_label"):
        return {}

    system_prompt = """You are a senior SOC analyst. A classifier has already assigned a \
verdict to this alert. Your job is to explain that verdict to a human analyst in plain \
English, grounded strictly in the evidence shown.

Rules:
- The verdict is already decided. Do not dispute it, revise it, or offer an alternative.
- Cite only fields that actually appear in the alert context below. Never invent evidence.
- If the evidence is thin, say so plainly -- "the verdict rests on a weak signal" is a
  useful thing for an analyst to read, and far better than inventing support for it.
- Note anything a human should check before acting.
- Write 2-3 sentences of prose. No JSON, no bullet points, no preamble."""

    user_message = (
        f"Alert:\n\n{state['alert_context']}\n\n"
        f"Assigned verdict: {state['predicted_label']}\n"
        f"Classifier confidence: {state.get('confidence', 'unknown')}\n\n"
        "Explain this verdict for the analyst who has to action it."
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    last_error = None
    for attempt in range(MAX_LLM_RETRIES):
        try:
            response = llm.invoke(messages)
            return {
                "llm_response": response.content,
                "rationale": (response.content or "").strip(),
                "rationale_status": "generated",
            }
        except Exception as e:
            last_error = str(e)
            if "rate_limit_exceeded" in last_error or "429" in last_error:
                time.sleep(_extract_retry_seconds(last_error))
                continue
            break

    # Explanation is a presentation concern, so its failure must not become a
    # triage error -- writing `error` here would wrongly mark a perfectly good
    # RF verdict as a failed alert.
    return {
        "rationale": None,
        "rationale_status": "unavailable",
        "llm_response": f"[explanation unavailable: {last_error}]",
    }


def route_after_rf_verdict(state: AlertState) -> str:
    """Send low-margin RF verdicts to a human before they are acted on.

    Gates on the RF's decision margin, not on any model's self-report. Alerts
    that failed earlier (no verdict at all) always go to review.
    """
    if state.get("error") or not state.get("predicted_label"):
        return "human_review"
    margin = state.get("rf_margin")
    if margin is None or margin < RF_REVIEW_MARGIN_THRESHOLD:
        return "human_review"
    return "end"
