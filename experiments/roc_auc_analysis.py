# experiments/roc_auc_analysis.py
#
# ROC/AUC has never been computed anywhere in this repo for the live RF/LLM
# pipeline. The RF already exposes predict_proba (used for the margin gate
# in fallback_classifier.py), so a multiclass one-vs-rest ROC/AUC is
# straightforward to add -- it just has never been asked for until now.
#
# Two callers use compute_ovr_roc_auc():
#   * this script's own --source control_209, which RE-SCORES the 209-alert
#     control set (rf_vs_llm_control.json's per_alert_results only stored
#     top-1 probability/margin, not the full class-probability vector this
#     needs) and writes experiments/results/roc_auc_control_209.json.
#   * experiments/guide_test_holdout_eval.py, which imports the helper
#     directly and folds the result into its own output file.
#
# The LLM has no calibrated probability output -- a discrete
# {"high","medium","low"} self-report is not a score you can sweep a
# threshold over, so ROC/AUC is not defined for it. Its honest analog is
# calibration_table() in rf_vs_llm_control.py (confidence band vs empirical
# accuracy), reused here rather than duplicated. Do not fabricate an LLM AUC
# by treating confidence bands as a numeric score; that would misrepresent
# what was measured.
#
# Everything here is offline. No API calls.
#
# usage (from repo root):
#   venv/bin/python experiments/roc_auc_analysis.py --source control_209

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve

from src.agent.fallback_classifier import _load_model, _to_feature_frame, should_use_fallback

CACHE_PATH = Path(
    "experiments/results/evaluation_samples/guide_balanced_333_per_class_seed_42.csv"
)
LLM_RESULTS_PATH = Path("experiments/results/llm_subset_eval_improved_full209.json")
OUTPUT_PATH = Path("experiments/results/roc_auc_control_209.json")


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def compute_ovr_roc_auc(
    y_true: list[str], proba_matrix: np.ndarray, classes: list[str]
) -> dict:
    """One-vs-rest ROC/AUC for a multiclass classifier with full class probabilities.

    `classes` must be in the same column order as `proba_matrix` (i.e. the
    order the model's own `.classes_` attribute uses) -- getting this order
    wrong silently mislabels every per-class curve without raising.

    Returns per-class AUC + ROC curve points, and a macro-averaged AUC (the
    multiclass generalisation reported as "the classifier's ROC-AUC").
    Requires a full probability vector per row, not a top-1 score alone.
    """
    y_true_arr = np.asarray(y_true)
    proba = np.asarray(proba_matrix)
    macro_auc = roc_auc_score(
        y_true_arr, proba, multi_class="ovr", average="macro", labels=list(classes)
    )
    per_class = {}
    for idx, cls in enumerate(classes):
        y_binary = (y_true_arr == cls).astype(int)
        fpr, tpr, _ = roc_curve(y_binary, proba[:, idx])
        class_auc = roc_auc_score(y_binary, proba[:, idx])
        per_class[cls] = {
            "auc": round(float(class_auc), 4),
            "fpr": [round(float(v), 4) for v in fpr],
            "tpr": [round(float(v), 4) for v in tpr],
            "n_positive": int(y_binary.sum()),
            "n_negative": int(len(y_binary) - y_binary.sum()),
        }
    return {
        "classes": list(classes),
        "macro_auc": round(float(macro_auc), 4),
        "per_class": per_class,
        "note": (
            "Macro one-vs-rest AUC over the RandomForest's predict_proba output. "
            "No LLM AUC is reported: the LLM's self-reported confidence "
            "(high/medium/low) is not a calibrated probability, so ROC/AUC is "
            "not defined for it. See llm_confidence_calibration in "
            "rf_vs_llm_control.py for its honest analog."
        ),
    }


def rescore_control_209() -> dict:
    """Re-score the 209-alert control set, capturing full predict_proba vectors.

    Reproduces the same LLM-eligible subset and the same verification-against
    -committed-results check as experiments/rf_vs_llm_control.py, because
    that file's own per_alert_results only kept the RF's top-1
    probability/margin -- not enough for ROC/AUC, which needs the full
    per-class probability vector.
    """
    cache = pd.read_csv(CACHE_PATH)
    eligible = cache[cache.apply(lambda r: not should_use_fallback(r.to_dict()), axis=1)]

    llm_results = json.loads(LLM_RESULTS_PATH.read_text())["per_alert_results"]
    llm_by_index = {r["_row_index"]: r for r in llm_results}
    if set(llm_by_index) != set(eligible.index):
        raise RuntimeError(
            "The LLM-routed subset reproduced from should_use_fallback does not "
            "match the rows in the committed LLM results file -- same check as "
            "rf_vs_llm_control.py. Do not report a mismatched comparison."
        )

    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]
    classes = [str(c) for c in model.classes_]

    y_true, proba_rows = [], []
    for _, row in eligible.iterrows():
        alert = row.to_dict()
        ground_truth = alert.pop("IncidentGrade")
        features = _to_feature_frame(alert, model, encoders)
        proba = model.predict_proba(features)[0]
        y_true.append(ground_truth)
        proba_rows.append(proba)

    proba_matrix = np.array(proba_rows)
    roc = compute_ovr_roc_auc(y_true, proba_matrix, classes=classes)
    return {
        "n": len(y_true),
        "evaluation_sample": str(CACHE_PATH),
        "subset": "LLM-eligible (evidence_field_count >= 2), same 209 rows as rf_vs_llm_control.json",
        "model_classes": classes,
        "roc_auc": roc,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute RF ROC/AUC (multiclass, one-vs-rest).")
    parser.add_argument("--source", choices=["control_209"], default="control_209")
    args = parser.parse_args()

    if args.source == "control_209":
        result = rescore_control_209()
        output = {
            "experiment": "RandomForest ROC/AUC on the 209-alert control set",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha(),
            "finding": (
                f"Macro one-vs-rest AUC {result['roc_auc']['macro_auc']} over "
                f"{result['n']} alerts (the same LLM-eligible subset scored in "
                "rf_vs_llm_control.json). No LLM AUC is reported -- see the "
                "note field for why."
            ),
            **result,
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(output, indent=2))
        print(f"macro AUC: {result['roc_auc']['macro_auc']}")
        for cls, block in result["roc_auc"]["per_class"].items():
            print(f"  {cls}: AUC {block['auc']} (n+={block['n_positive']}, n-={block['n_negative']})")
        print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
