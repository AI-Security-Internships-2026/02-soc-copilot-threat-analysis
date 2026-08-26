# experiments/llm_subset_eval.py
#
# Week 12: diagnostic + prompt-improvement eval scoped to exactly the alerts
# the hybrid pipeline routes to the LLM (evidence_field_count >= 2, see
# src/agent/fallback_classifier.py). Motivation: analysis of the existing
# 999-sample hybrid run (experiments/results/agent_metrics_week6_fallback_rerun.json)
# showed the LLM-routed subset scores only 0.36 accuracy / 0.31 macro F1 --
# barely above chance for a 3-class problem -- even though these are
# specifically the alerts with the *most* analyst-readable context (Suspicion
# Level, Last Verdict, MITRE technique). That run used the now-deprecated
# llama-3.1-8b-instant model (retired from Groq, see Week 11). This script
# re-measures the same LLM-eligible alerts with the current production model
# (openai/gpt-oss-20b) and, optionally, an improved prompt, to see whether
# either closes the gap.
#
# usage (run from repo root):
#   venv/bin/python experiments/llm_subset_eval.py --prompt baseline --n-per-class 20
#   venv/bin/python experiments/llm_subset_eval.py --prompt improved --n-per-class 20

import argparse
import json
import sys
import time
from pathlib import Path

# make sure repo root is importable regardless of where this is run from
# (same fix as experiments/soc_domain_eval.py, experiments/deepteam_redteam_eval.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from sklearn.metrics import accuracy_score, classification_report, f1_score

from src.agent.fallback_classifier import should_use_fallback
from src.agent.nodes import MAX_LLM_RETRIES, _extract_retry_seconds, _has_value, llm

CACHE_PATH = Path("experiments/results/evaluation_samples/guide_balanced_333_per_class_seed_42.csv")

BASELINE_SYSTEM_PROMPT = """You are a senior SOC analyst. Your job is to triage cybersecurity alerts.

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

# Improved variant: (1) explicitly tells the model which fields are the
# strongest signal instead of presenting an undifferentiated context blob --
# Suspicion Level / Last Verdict are analyst/system judgements from the GUIDE
# telemetry pipeline itself, not raw noise; (2) adds one grounded few-shot
# example per class using real GUIDE-style field values (numeric AlertTitle,
# MITRE technique IDs, Category tactics) instead of a generic SOC scenario,
# since the domain-mismatch finding (Week 8/9) showed generic SOC assumptions
# don't transfer to GUIDE's schema; (3) puts "reasoning" before "verdict" in
# the JSON schema to encourage the model to write out its reasoning before
# committing, rather than backfilling a rationale after the fact.
IMPROVED_SYSTEM_PROMPT = """You are a senior SOC analyst triaging alerts from the Microsoft GUIDE \
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

PROMPTS = {"baseline": BASELINE_SYSTEM_PROMPT, "improved": IMPROVED_SYSTEM_PROMPT}


def build_alert_context(alert: dict) -> str:
    """Mirrors src/agent/nodes.py's build_context() exactly (not imported
    directly since that function reads from graph state, not a plain dict),
    including the Week 12 _has_value() fix -- a bare truthiness check treats
    a missing-data NaN float as present, which used to render a literal
    "MITRE Technique: nan" / "Suspicion Level: nan" line into the prompt."""
    parts = []
    if _has_value(alert.get("AlertTitle")):
        parts.append(f"Alert Title: {alert['AlertTitle']}")
    if _has_value(alert.get("Category")):
        parts.append(f"Category: {alert['Category']}")
    if _has_value(alert.get("MitreTechniques")):
        parts.append(f"MITRE Technique: {alert['MitreTechniques']}")
    if _has_value(alert.get("DetectorId")):
        parts.append(f"Detector: {alert['DetectorId']}")
    if _has_value(alert.get("SuspicionLevel")):
        parts.append(f"Suspicion Level: {alert['SuspicionLevel']}")
    if _has_value(alert.get("LastVerdict")):
        parts.append(f"Last Verdict: {alert['LastVerdict']}")
    return "\n".join(parts) if parts else "No alert details available."


def classify(alert_context: str, system_prompt: str) -> dict:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Triage this alert:\n\n{alert_context}"),
    ]
    last_error = None
    for _ in range(MAX_LLM_RETRIES):
        try:
            response = llm.invoke(messages)
            raw = response.content
            break
        except Exception as e:
            last_error = str(e)
            if "rate_limit_exceeded" in last_error or "429" in last_error:
                time.sleep(_extract_retry_seconds(last_error))
                continue
            return {"predicted_label": None, "error": last_error}
    else:
        return {"predicted_label": None, "error": f"failed after {MAX_LLM_RETRIES} attempts: {last_error}"}

    try:
        clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
        parsed = json.loads(clean)
        verdict = parsed.get("verdict", "FalsePositive")
        if verdict not in {"TruePositive", "BenignPositive", "FalsePositive"}:
            verdict = None
        return {"predicted_label": verdict, "confidence": parsed.get("confidence"), "reasoning": parsed.get("reasoning"), "raw": raw}
    except (json.JSONDecodeError, AttributeError) as e:
        return {"predicted_label": None, "error": f"parse error: {e}", "raw": raw}


def load_llm_eligible_sample(n_per_class: int, seed: int = 42) -> pd.DataFrame:
    df = pd.read_csv(CACHE_PATH)
    df = df[df.apply(lambda r: not should_use_fallback(r.to_dict()), axis=1)]
    return (
        df.groupby("IncidentGrade", group_keys=False)
        .apply(lambda g: g.sample(n=min(n_per_class, len(g)), random_state=seed))
        .reset_index(drop=True)
    )


def run(prompt_variant: str, n_per_class: int, output_path: str):
    system_prompt = PROMPTS[prompt_variant]
    sample = load_llm_eligible_sample(n_per_class)
    print(f"running '{prompt_variant}' prompt on {len(sample)} LLM-eligible alerts "
          f"({n_per_class}/class, evidence_field_count >= 2)...")

    y_true, y_pred, log = [], [], []
    for i, row in sample.iterrows():
        alert = row.to_dict()
        ground_truth = alert.pop("IncidentGrade")
        context = build_alert_context(alert)
        result = classify(context, system_prompt)
        predicted = result.get("predicted_label")
        log.append({"ground_truth": ground_truth, **result})
        if predicted is not None:
            y_true.append(ground_truth)
            y_pred.append(predicted)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(sample)}...")
        time.sleep(0.3)

    accuracy = accuracy_score(y_true, y_pred) if y_true else None
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0) if y_true else None
    report = classification_report(y_true, y_pred, zero_division=0) if y_true else "no scorable predictions"
    print(f"\n=== {prompt_variant} prompt, LLM-eligible subset ===")
    print(f"accuracy: {accuracy}\nmacro_f1: {macro_f1}\n{report}")

    output = {
        "prompt_variant": prompt_variant,
        "n_sampled": len(sample),
        "n_scored": len(y_true),
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "macro_f1": round(macro_f1, 4) if macro_f1 is not None else None,
        "classification_report": report,
        "per_alert_results": log,
    }
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"saved to {output_path}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate the LLM node on exactly its own routed subset")
    parser.add_argument("--prompt", choices=list(PROMPTS), default="baseline")
    parser.add_argument("--n-per-class", type=int, default=20)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()
    output_path = args.output or f"experiments/results/llm_subset_eval_{args.prompt}.json"
    run(args.prompt, args.n_per_class, output_path)
