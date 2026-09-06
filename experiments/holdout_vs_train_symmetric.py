# experiments/holdout_vs_train_symmetric.py
#
# How much accuracy does the Random Forest lose on alerts from Microsoft's
# held-out GUIDE_Test.csv split, compared with alerts sampled from the file it
# was trained on?
#
# The comparison already existed in guide_test_holdout_eval.py, but at
# mismatched sample sizes: n=15,000 held-out against n=999 train-sampled. A gap
# measured that way confounds the effect of interest with the much wider
# sampling error on the smaller side. experiments/large_train_sampled_rf_eval.py
# was written to close that -- it scores a train-sampled set at the same
# n=15,000 -- and this script is the symmetric test the pair was built for.
#
# It was missing. experiments/results/holdout_vs_train_symmetric_15000.json is
# cited by docs/final-report.md but until Week 17 no committed script produced
# it, so the numbers in it could not be checked or re-derived by a reader. This
# script closes that gap. It reads the two committed result files, takes the
# per-alert rows from each, and recomputes the interval directly.
#
# Both sides are scored by the same static model on different alerts, so this
# is a two-sample bootstrap on the difference -- NOT McNemar's test, which
# needs the same rows scored two ways. See the docstring on
# bootstrap_two_sample_diff_ci() in experiments/stats_utils.py.
#
# Note what the gap does and does not mean: the train-sampled side is itself
# contaminated. GUIDE's label is incident-level, and 55.76% of any
# train-sampled evaluation set shares an incident with the training slice
# (experiments/incident_leakage_audit.py). So this gap is a lower bound on the
# real generalisation cost, measured between a clean sample and a leaky one.
#
# usage (from repo root, offline, ~2 minutes):
#   venv/bin/python experiments/holdout_vs_train_symmetric.py

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.metrics import accuracy_score, f1_score

from experiments.stats_utils import bootstrap_two_sample_diff_ci

HELD_OUT_PATH = Path("experiments/results/guide_test_holdout_eval.json")
TRAIN_SAMPLED_PATH = Path("experiments/results/large_train_sampled_rf_eval.json")
OUTPUT_PATH = Path("experiments/results/holdout_vs_train_symmetric_15000.json")


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _rows(path: Path, *block_candidates: str) -> list[dict]:
    """Per-alert rows out of a committed result file, whichever block holds them."""
    if not path.exists():
        raise SystemExit(f"{path} is missing; run the script that produces it first.")
    payload = json.loads(path.read_text())
    for block in block_candidates:
        rows = (payload.get(block) or {}).get("per_alert_results")
        if rows:
            return rows
    raise SystemExit(
        f"{path} has no per_alert_results under any of {block_candidates}; "
        f"it may have been produced by an older version of its script."
    )


def main() -> None:
    held_out = _rows(HELD_OUT_PATH, "test_holdout")
    train_sampled = _rows(TRAIN_SAMPLED_PATH, "train_sampled")

    if len(held_out) != len(train_sampled):
        print(
            f"warning: sides are not the same size ({len(held_out)} vs "
            f"{len(train_sampled)}). The point of this script is a symmetric "
            f"comparison; regenerate both sides at matched n."
        )

    y_true_a = [r["ground_truth"] for r in held_out]
    y_pred_a = [r["rf_predicted"] for r in held_out]
    y_true_b = [r["ground_truth"] for r in train_sampled]
    y_pred_b = [r["rf_predicted"] for r in train_sampled]

    print(f"held-out      n={len(y_true_a)}  ({HELD_OUT_PATH})")
    print(f"train-sampled n={len(y_true_b)}  ({TRAIN_SAMPLED_PATH})")
    print("bootstrapping the accuracy gap...")
    accuracy_gap = bootstrap_two_sample_diff_ci(
        y_true_a, y_pred_a, y_true_b, y_pred_b, metric_fn=accuracy_score
    )
    print("bootstrapping the macro F1 gap...")
    macro_f1_gap = bootstrap_two_sample_diff_ci(
        y_true_a, y_pred_a, y_true_b, y_pred_b,
        metric_fn=lambda t, p: f1_score(t, p, average="macro", zero_division=0),
    )

    n = len(y_true_a)
    output = {
        "experiment": f"Symmetric (n={n} vs n={len(y_true_b)}) held-out vs train-sampled RF generalisation gap",
        "question": (
            "The earlier held-out-vs-train comparison used mismatched sample "
            "sizes (n=15000 held-out vs n=999 train-sampled), which confounds "
            "the gap with sampling error on the smaller side. This repeats it "
            "at matched n on both sides."
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "held_out_source": f"{HELD_OUT_PATH} (n={len(y_true_a)})",
        "train_sampled_source": f"{TRAIN_SAMPLED_PATH} (n={len(y_true_b)})",
        "leakage_caveat": (
            "A lower bound on the generalisation cost, not the whole of it. The "
            "train-sampled side is itself contaminated: GUIDE's label is "
            "incident-level and 55.76% of a train-sampled evaluation set shares "
            "an incident with the training slice, worth +24.3 accuracy points "
            "(experiments/incident_leakage_audit.py). This gap is measured "
            "between a clean sample and a leaky one."
        ),
        "accuracy_gap": accuracy_gap,
        "macro_f1_gap": macro_f1_gap,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\n  accuracy : {accuracy_gap['point_a']} vs {accuracy_gap['point_b']}  "
          f"diff {accuracy_gap['point_diff']:+.4f} "
          f"95% CI [{accuracy_gap['ci_lower']:+.4f}, {accuracy_gap['ci_upper']:+.4f}]")
    print(f"  macro F1 : {macro_f1_gap['point_a']} vs {macro_f1_gap['point_b']}  "
          f"diff {macro_f1_gap['point_diff']:+.4f} "
          f"95% CI [{macro_f1_gap['ci_lower']:+.4f}, {macro_f1_gap['ci_upper']:+.4f}]")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
