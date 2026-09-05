# experiments/rf_vs_llm_control.py
#
# Week 15: the control experiment that decides whether the LLM belongs on the
# triage decision path at all.
#
# Motivation. Every prior comparison in this project measured the LLM and the
# RandomForest on *different* alerts. The hybrid pipeline routes sparse alerts
# to the RF and well-evidenced alerts to the LLM (see should_use_fallback in
# src/agent/fallback_classifier.py), so "LLM subset scored 0.28, RF subset
# scored 0.75" has an obvious confound: maybe the LLM-routed alerts are simply
# harder. That confound has never been eliminated, and it is the single thing
# standing between us and an evidence-based architecture decision.
#
# This script eliminates it. It scores the RandomForest on the *exact same*
# 209 alerts the LLM was scored on -- same rows, same ground truth, same class
# balance -- so the two systems differ only in which model produced the label.
#
# Because both systems are evaluated on identical samples, the correct
# significance test is McNemar's paired test on the discordant pairs, not a
# two-proportion z-test (which assumes independent samples and would overstate
# the p-value here).
#
# Everything runs offline from committed artifacts. No Groq API calls, no
# quota risk.
#
# usage (from repo root):
#   venv/bin/python experiments/rf_vs_llm_control.py

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.metrics import accuracy_score, classification_report, f1_score

from src.agent.fallback_classifier import (
    _load_model,
    _to_feature_frame,
    should_use_fallback,
)
from src.models.decision import resolve_label

CACHE_PATH = Path(
    "experiments/results/evaluation_samples/guide_balanced_333_per_class_seed_42.csv"
)
LLM_RESULTS_PATH = Path("experiments/results/llm_subset_eval_improved_full209.json")
OUTPUT_PATH = Path("experiments/results/rf_vs_llm_control.json")

# The RF baseline is trained on the first 100k rows of GUIDE_train.csv
# (src/models/baseline.py). The evaluation cache is sampled from all 9.5M rows
# of the same file, so some overlap is possible and must be reported rather
# than assumed away.
RF_TRAIN_ROWS = 100_000
CLASSES = ("BenignPositive", "FalsePositive", "TruePositive")


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def rf_predict_with_margin(alert: dict, model, encoders: dict) -> tuple[str, float, float]:
    """Return (label, top-1 probability, top1-minus-top2 margin) for one alert.

    The margin is the quantity we care about for gating. A max probability of
    0.45 means something very different when the runner-up is 0.44 (a coin
    flip) than when it is 0.10 (a clear call), and the existing pipeline's
    confidence bands cannot tell those apart.
    """
    features = _to_feature_frame(alert, model, encoders)
    probabilities = model.predict_proba(features)[0]
    order = np.argsort(probabilities)[::-1]
    label = resolve_label(model.classes_, probabilities)
    top1 = float(probabilities[order[0]])
    top2 = float(probabilities[order[1]]) if len(probabilities) > 1 else 0.0
    return label, top1, top1 - top2


def score(y_true: list[str], y_pred: list[str]) -> dict:
    return {
        "n": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
        "classification_report": classification_report(
            y_true, y_pred, zero_division=0, digits=3
        ),
    }


def reference_baselines(y_true: list[str]) -> dict:
    """The floors every reported accuracy must be read against.

    A 3-class problem is not automatically a 33% floor: if one class holds 49%
    of the rows, then 'always guess that class' scores 49%, and any model below
    that is worse than a constant.
    """
    counts = Counter(y_true)
    n = len(y_true)
    majority_class, majority_n = counts.most_common(1)[0]
    # Expected accuracy of guessing uniformly at random over the 3 labels.
    uniform_random = round(sum((c / n) * (1 / 3) for c in counts.values()), 4)
    return {
        "class_distribution": dict(counts),
        "majority_class": majority_class,
        "majority_class_accuracy": round(majority_n / n, 4),
        "uniform_random_accuracy": uniform_random,
    }


def mcnemar(rf_correct: list[bool], llm_correct: list[bool]) -> dict:
    """Exact McNemar test on the paired correct/incorrect outcomes.

    Only the discordant pairs carry information: cases where one model was
    right and the other wrong. Under the null hypothesis that the two models
    are equally accurate, each discordant pair is a fair coin flip, so an exact
    binomial test on b vs c is the right test (and is valid at the small
    discordant counts where the chi-square approximation is not).
    """
    both_right = sum(r and l for r, l in zip(rf_correct, llm_correct))
    rf_only = sum(r and not l for r, l in zip(rf_correct, llm_correct))
    llm_only = sum(l and not r for r, l in zip(rf_correct, llm_correct))
    both_wrong = sum((not r) and (not l) for r, l in zip(rf_correct, llm_correct))
    discordant = rf_only + llm_only
    p_value = (
        binomtest(rf_only, discordant, 0.5).pvalue if discordant > 0 else 1.0
    )
    return {
        "both_correct": both_right,
        "rf_correct_llm_wrong": rf_only,
        "llm_correct_rf_wrong": llm_only,
        "both_wrong": both_wrong,
        "discordant_pairs": discordant,
        # round(p, 6) collapsed every p-value below 5e-7 to 0.0. This test
        # routinely produces them (p=4.66e-12 on the 209-alert control set),
        # so the headline significance figure survived only inside the prose
        # `interpretation` string below and could not be read back
        # programmatically. Keep the full float, and a scientific-notation
        # string beside it for anything that formats the JSON directly.
        "p_value": float(p_value),
        "p_value_scientific": f"{float(p_value):.3e}",
        "interpretation": (
            f"Of the {discordant} alerts where the two models disagreed in "
            f"correctness, the RF was the correct one in {rf_only}. Under the "
            f"null hypothesis that both models are equally accurate this split "
            f"has p = {float(p_value):.2e}."
        ),
    }


def calibration_table(rows: list[dict]) -> dict:
    """Accuracy within each self-reported LLM confidence band.

    The pipeline escalates to a human only when confidence is NOT high
    (route_after_verdict in src/agent/nodes.py). That is only a safety net if
    high-confidence predictions are actually more accurate than low-confidence
    ones. This table checks that assumption instead of trusting it.
    """
    bands: dict[str, list[bool]] = {}
    for r in rows:
        band = r.get("confidence") or "none"
        bands.setdefault(band, []).append(r.get("predicted_label") == r["ground_truth"])
    table = {
        band: {
            "n": len(hits),
            "correct": sum(hits),
            "accuracy": round(sum(hits) / len(hits), 4),
        }
        for band, hits in sorted(bands.items())
    }
    auto_accepted = [r for r in rows if r.get("confidence") == "high"]
    escalated = [r for r in rows if r.get("confidence") != "high"]

    def acc(subset):
        if not subset:
            return None
        return round(
            sum(r.get("predicted_label") == r["ground_truth"] for r in subset)
            / len(subset),
            4,
        )

    return {
        "by_band": table,
        "gate_behaviour": {
            "auto_accepted_n": len(auto_accepted),
            "auto_accepted_accuracy": acc(auto_accepted),
            "escalated_to_human_n": len(escalated),
            "escalated_accuracy": acc(escalated),
            "gate_is_inverted": (acc(auto_accepted) or 0) < (acc(escalated) or 0),
        },
    }


def margin_gate_analysis(margins: list[float], rf_correct: list[bool]) -> dict:
    """Pick the human-review threshold from data rather than by feel.

    For each candidate margin threshold, report what fraction of alerts would
    be escalated and how accurate the auto-accepted remainder would be. A
    usable gate is one where auto-accepted accuracy rises meaningfully while
    the escalation rate stays affordable for a human team.
    """
    sweep = []
    for threshold in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50):
        auto = [c for m, c in zip(margins, rf_correct) if m >= threshold]
        escalated = len(margins) - len(auto)
        sweep.append(
            {
                "margin_threshold": threshold,
                "auto_accepted_n": len(auto),
                "auto_accepted_accuracy": round(sum(auto) / len(auto), 4) if auto else None,
                "escalated_n": escalated,
                "escalation_rate": round(escalated / len(margins), 4),
            }
        )
    return {"sweep": sweep}


def training_overlap(subset: pd.DataFrame) -> dict:
    """How much of this evaluation set the RF has already been shown.

    Reported rather than assumed: the RF trains on the first 100k rows of
    GUIDE_train.csv, and this evaluation samples the whole file, so overlap is
    possible in principle and would inflate the RF's score if large.

    Measured two ways, because the first one alone is misleading:

      exact-row     -- the row appears verbatim in the training slice. This
                       is the 1.91% figure this project has published since
                       Week 15 and judged immaterial.
      incident-level -- the row's (OrgId, IncidentId) appears in the training
                       slice, so a sibling evidence row carrying the SAME
                       label was available during training. GUIDE labels are
                       incident-level and constant within an incident
                       (verified in experiments/incident_leakage_audit.py),
                       so this, not exact-row equality, is what determines
                       whether the answer was recoverable from training data.

    The two differ by roughly an order of magnitude, which is why reporting
    only the first understates the contamination.
    """
    columns = [c for c in subset.columns if c != "IncidentGrade"]
    train_head = pd.read_csv(
        "datasets/GUIDE_train.csv", nrows=RF_TRAIN_ROWS, usecols=columns, low_memory=False
    )
    train_keys = set(map(tuple, train_head.astype(str).values))
    subset_keys = list(map(tuple, subset[columns].astype(str).values))
    overlap = sum(k in train_keys for k in subset_keys)

    train_incidents = set(zip(train_head["OrgId"], train_head["IncidentId"]))
    subset_incidents = list(zip(subset["OrgId"], subset["IncidentId"]))
    incident_overlap = sum(k in train_incidents for k in subset_incidents)

    return {
        "rf_training_rows_checked": RF_TRAIN_ROWS,
        "evaluation_rows": len(subset_keys),
        "exact_row_overlap": overlap,
        "overlap_rate": round(overlap / len(subset_keys), 4),
        "incident_level_overlap": incident_overlap,
        "incident_level_overlap_rate": round(incident_overlap / len(subset_incidents), 4),
        "interpretation": (
            f"{overlap}/{len(subset_keys)} "
            f"({overlap / len(subset_keys):.2%}) of these alerts appear verbatim in "
            f"the training slice, but {incident_overlap}/{len(subset_incidents)} "
            f"({incident_overlap / len(subset_incidents):.2%}) belong to an incident "
            f"the model saw a labelled row from. The RF's score on this set should "
            f"be read with the second figure, not the first. See "
            f"experiments/incident_leakage_audit.py for the effect this has on "
            f"accuracy."
        ),
    }


def main() -> None:
    print("loading the 999-alert balanced evaluation cache...")
    cache = pd.read_csv(CACHE_PATH)

    # Reproduce the LLM-eligible subset deterministically from the routing rule
    # itself, rather than trusting a stored row list. This is verified against
    # the committed LLM results below.
    eligible = cache[cache.apply(lambda r: not should_use_fallback(r.to_dict()), axis=1)]
    print(f"  {len(cache)} cached alerts -> {len(eligible)} routed to the LLM")

    llm_results = json.loads(LLM_RESULTS_PATH.read_text())["per_alert_results"]
    llm_by_index = {r["_row_index"]: r for r in llm_results}
    if set(llm_by_index) != set(eligible.index):
        raise RuntimeError(
            "The LLM-routed subset reproduced from should_use_fallback does not "
            "match the rows in the committed LLM results file. The routing rule "
            "or the cache has changed since that run; the comparison would not "
            "be paired and must not be reported."
        )
    print("  verified: reproduced subset matches the committed LLM run exactly")

    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    y_true, rf_pred, llm_pred, margins, per_alert = [], [], [], [], []
    print(f"scoring the RandomForest on the same {len(eligible)} alerts...")
    for row_index, row in eligible.iterrows():
        alert = row.to_dict()
        ground_truth = alert.pop("IncidentGrade")
        label, top1, margin = rf_predict_with_margin(alert, model, encoders)
        llm_row = llm_by_index[row_index]

        y_true.append(ground_truth)
        rf_pred.append(label)
        llm_pred.append(llm_row.get("predicted_label"))
        margins.append(margin)
        per_alert.append(
            {
                "_row_index": int(row_index),
                "ground_truth": ground_truth,
                "rf_predicted": label,
                "rf_top1_probability": round(top1, 4),
                "rf_margin": round(margin, 4),
                "llm_predicted": llm_row.get("predicted_label"),
                "llm_confidence": llm_row.get("confidence"),
            }
        )

    rf_correct = [p == t for p, t in zip(rf_pred, y_true)]
    llm_correct = [p == t for p, t in zip(llm_pred, y_true)]

    rf_scores = score(y_true, rf_pred)
    llm_scores = score(y_true, llm_pred)
    baselines = reference_baselines(y_true)

    print("\ncomputing exact-row and incident-level overlap with the RF training slice...")
    overlap = training_overlap(eligible)

    output = {
        "experiment": "RandomForest vs LLM on the identical LLM-routed alert subset",
        "question": (
            "Prior comparisons scored the two models on different alerts, so a "
            "lower LLM score could have meant the LLM-routed alerts were "
            "harder. This scores both models on the same rows to remove that "
            "confound."
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "rf_model": "RandomForestClassifier, experiments/results/baseline_model.joblib",
        "llm_model": "openai/gpt-oss-20b (Groq), improved prompt",
        "llm_results_source": str(LLM_RESULTS_PATH),
        "evaluation_sample": str(CACHE_PATH),
        "routing_rule": "evidence_field_count >= 2 (src/agent/fallback_classifier.py)",
        "reference_baselines": baselines,
        "randomforest": rf_scores,
        "llm": llm_scores,
        "paired_mcnemar_test": mcnemar(rf_correct, llm_correct),
        "llm_confidence_calibration": calibration_table(llm_results),
        "rf_margin_gate_analysis": margin_gate_analysis(margins, rf_correct),
        "rf_training_overlap": overlap,
        "per_alert_results": per_alert,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 68)
    print(f"SAME {len(y_true)} ALERTS, TWO MODELS")
    print("=" * 68)
    print(f"  RandomForest : accuracy {rf_scores['accuracy']}   macro F1 {rf_scores['macro_f1']}")
    print(f"  LLM          : accuracy {llm_scores['accuracy']}   macro F1 {llm_scores['macro_f1']}")
    print(f"  majority-class floor : {baselines['majority_class_accuracy']} "
          f"(always answer {baselines['majority_class']})")
    print(f"  uniform-random floor : {baselines['uniform_random_accuracy']}")
    print(f"\n  McNemar: {output['paired_mcnemar_test']['interpretation']}")
    cal = output["llm_confidence_calibration"]["gate_behaviour"]
    print(f"\n  Confidence gate: auto-accepts {cal['auto_accepted_n']} alerts at "
          f"{cal['auto_accepted_accuracy']} accuracy,")
    print(f"                   escalates {cal['escalated_to_human_n']} at "
          f"{cal['escalated_accuracy']} accuracy.")
    print(f"                   inverted: {cal['gate_is_inverted']}")
    print(f"\n  RF training overlap, exact-row    : {overlap['exact_row_overlap']}/{overlap['evaluation_rows']} "
          f"({overlap['overlap_rate']:.2%})")
    print(f"  RF training overlap, incident-lvl: {overlap['incident_level_overlap']}/{overlap['evaluation_rows']} "
          f"({overlap['incident_level_overlap_rate']:.2%})  <- the figure that matters")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
