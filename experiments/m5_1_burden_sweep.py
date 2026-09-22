"""
M5.1 PART B -- human-in-the-loop burden sweep and its Pareto frontier.

Issue #42. RQ3 asked for the accuracy/human-burden trade-off, and this answers
it: as the RF margin threshold T rises, fewer alerts are auto-accepted (less
analyst time saved) but the ones that are get more accurate.

Measured on the class-balanced GUIDE_Test.csv hold-out (n=15,000, 0% incident
overlap), not on a train-sampled set -- an operating point chosen on leaked data
would recommend a threshold that does not hold in deployment. Scoring reuses the
deployed path (`fallback_classifier._load_model` / `_to_feature_frame` and the
shared tie-break in `models.decision.resolve_label`), so the margins here are the
ones the running system computes.

**The hybrid column is a projection, not a measurement.** Total system accuracy
assumes an escalated alert is resolved correctly by a human with probability
HUMAN_ACC. No human-accuracy study has been run on this project, so that number
is an assumption carried from the issue, and the column is labelled as such
wherever it appears. The auto-accepted and escalated columns are measured.

Run:  venv/bin/python experiments/m5_1_burden_sweep.py
      venv/bin/python experiments/m5_1_burden_sweep.py --sample-size 999   (quick)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import sys

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

# Match the other experiment scripts: run directly from the repo root, so the
# repo root has to go on the path before src/ imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.fallback_classifier import _load_model, _to_feature_frame
from src.data.schema import TARGET_COLUMN
from src.models.decision import resolve_label
from experiments.stats_utils import bootstrap_metric_ci

OUTPUT_JSON = Path("experiments/results/m5_1_burden_sweep.json")
OUTPUT_CSV = Path("experiments/results/m5_1_burden_sweep.csv")
CACHE = Path("experiments/results/evaluation_samples")

THRESHOLDS = [0.00, 0.02, 0.05, 0.10, 0.12, 0.15, 0.20, 0.30, 0.50]
RECOMMENDED_T = 0.12          # the issue's proposed operating point
HUMAN_ACC = 0.95              # ASSUMPTION, not measured -- see the module docstring
ACC = lambda t, p: accuracy_score(t, p)


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def score(sample: pd.DataFrame) -> pd.DataFrame:
    """Top-1 probability, margin and predicted label for every row."""
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]
    rows = []
    for _, row in sample.iterrows():
        alert = row.to_dict()
        truth = alert.pop(TARGET_COLUMN)
        proba = model.predict_proba(_to_feature_frame(alert, model, encoders))[0]
        ordered = np.sort(proba)[::-1]
        rows.append({
            "ground_truth": truth,
            "predicted": resolve_label(model.classes_, proba),
            "margin": float(ordered[0] - ordered[1]),
        })
    return pd.DataFrame(rows)


def sweep(scored: pd.DataFrame) -> list[dict]:
    n = len(scored)
    out = []
    for t in THRESHOLDS:
        auto = scored[scored["margin"] >= t]
        esc = scored[scored["margin"] < t]
        auto_acc = float((auto["ground_truth"] == auto["predicted"]).mean()) if len(auto) else None
        esc_acc = float((esc["ground_truth"] == esc["predicted"]).mean()) if len(esc) else None

        ci = (bootstrap_metric_ci(auto["ground_truth"].tolist(),
                                  auto["predicted"].tolist(), ACC, n_resamples=2000)
              if len(auto) >= 2 else None)

        auto_pct = len(auto) / n
        # Projection: auto-accepted alerts keep the model's accuracy; escalated
        # ones are resolved by a human at HUMAN_ACC. Assumption, not measurement.
        hybrid = (auto_pct * (auto_acc or 0.0)) + ((1 - auto_pct) * HUMAN_ACC)

        out.append({
            "T": t,
            "auto_accepted_n": int(len(auto)),
            "auto_accepted_pct": round(auto_pct, 4),
            "auto_accepted_accuracy": round(auto_acc, 4) if auto_acc is not None else None,
            "auto_accepted_accuracy_ci": [ci["ci_lower"], ci["ci_upper"]] if ci else None,
            "escalated_n": int(len(esc)),
            "escalated_pct": round(1 - auto_pct, 4),
            "escalated_accuracy_model_would_have_given": (
                round(esc_acc, 4) if esc_acc is not None else None),
            "projected_total_accuracy_assuming_human_at_0_95": round(hybrid, 4),
            "analyst_burden_saved_pct": round(auto_pct, 4),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-size", type=int, default=15000)
    args = ap.parse_args()

    per_class = args.sample_size // 3
    path = CACHE / f"guide_test_balanced_{per_class}_per_class_seed_42.csv"
    if not path.exists():
        raise SystemExit(
            f"{path} not found. Generate it first with:\n"
            f"  venv/bin/python experiments/guide_test_holdout_eval.py "
            f"--sample-size {args.sample_size}")

    sample = pd.read_csv(path, low_memory=False)
    print(f"scoring {len(sample)} held-out alerts through the deployed path...")
    scored = score(sample)

    overall = float((scored["ground_truth"] == scored["predicted"]).mean())
    table = sweep(scored)
    rec = next(r for r in table if r["T"] == RECOMMENDED_T)

    result = {
        "experiment": "M5.1 PART B -- HITL margin-threshold burden sweep",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "evaluation_set": str(path),
        "n": len(scored),
        "population_note": "class-balanced GUIDE_Test.csv hold-out, 0% incident "
                           "overlap with the training slice. Chosen deliberately: an "
                           "operating point tuned on a train-sampled set inherits the "
                           "incident-level leakage and would not hold in deployment.",
        "overall_accuracy_no_gate": round(overall, 4),
        "human_accuracy_assumption": HUMAN_ACC,
        "human_accuracy_assumption_note": (
            "ASSUMED, not measured. No human-accuracy study has been run on this "
            "project, so every 'projected_total_accuracy' figure is a projection "
            "conditional on this value. The auto-accepted and escalated accuracies "
            "are measured."),
        "recommended_operating_point": {
            "T": RECOMMENDED_T,
            **{k: rec[k] for k in ("auto_accepted_pct", "auto_accepted_accuracy",
                                   "escalated_pct",
                                   "projected_total_accuracy_assuming_human_at_0_95")},
        },
        "sweep": table,
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n")
    pd.DataFrame(table).to_csv(OUTPUT_CSV, index=False)

    print(f"\n  ungated accuracy on this set: {overall:.4f}  (n={len(scored)})")
    print(f"\n  {'T':>5} {'auto%':>7} {'auto acc':>9} {'esc%':>7} "
          f"{'esc acc':>8} {'proj total*':>12}")
    for r in table:
        star = "  <- recommended" if r["T"] == RECOMMENDED_T else ""
        print(f"  {r['T']:>5.2f} {r['auto_accepted_pct']:>7.1%} "
              f"{(r['auto_accepted_accuracy'] or 0):>9.4f} {r['escalated_pct']:>7.1%} "
              f"{(r['escalated_accuracy_model_would_have_given'] or 0):>8.4f} "
              f"{r['projected_total_accuracy_assuming_human_at_0_95']:>12.4f}{star}")
    print("\n  * projection assuming escalated alerts are resolved correctly "
          f"{HUMAN_ACC:.0%} of the time. Not measured.")
    print(f"\nwrote {OUTPUT_JSON}\nwrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
