# experiments/large_train_sampled_rf_eval.py
#
# The GUIDE_Test.csv holdout eval (guide_test_holdout_eval.py) was compared
# against a train-sampled reference at a mismatched scale (n=15,000 held-out
# vs n=999 train-sampled) -- an asymmetric comparison that understates the
# train-sampled side's own sampling uncertainty. This script closes that gap:
# same scoring logic (score_holdout, imported directly rather than
# duplicated), same bootstrap CI machinery, same class-balanced
# reservoir-sampling method, but drawn from GUIDE_train.csv at the same
# sample size as the held-out run, for a genuinely apples-to-apples
# comparison.
#
# Offline only (predict_proba on the already-trained baseline_model.joblib).
# No Groq calls -- this is purely about tightening the RF-side reference,
# not about the LLM.
#
# usage (from repo root):
#   venv/bin/python experiments/large_train_sampled_rf_eval.py --sample-size 15000

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.evaluate import load_balanced_evaluation_sample
from experiments.guide_test_holdout_eval import score_holdout

OUTPUT_PATH = Path("experiments/results/large_train_sampled_rf_eval.json")


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Large, class-balanced GUIDE_train.csv-sampled RF eval, "
        "sized to match a held-out run for a symmetric comparison."
    )
    parser.add_argument("--sample-size", type=int, default=15000)
    args = parser.parse_args()

    sample = load_balanced_evaluation_sample(args.sample_size).reset_index(drop=True)
    print(f"scoring {len(sample)} train-sampled alerts...")
    scores = score_holdout(sample)

    output = {
        "experiment": (
            "RandomForest evaluated on a large GUIDE_train.csv-sampled set, sized to match "
            "the GUIDE_Test.csv holdout run for a symmetric (not mismatched-n) comparison"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "rf_model": "RandomForestClassifier, experiments/results/baseline_model.joblib",
        "train_sampled": scores,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 68)
    print("LARGE TRAIN-SAMPLED RF EVALUATION")
    print("=" * 68)
    acc_ci = scores["accuracy_bootstrap_ci"]
    print(f"  accuracy: {scores['accuracy']} (95% CI [{acc_ci['ci_lower']}, {acc_ci['ci_upper']}])   macro F1: {scores['macro_f1']}")
    print(f"  macro AUC: {scores['roc_auc']['macro_auc']}")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
