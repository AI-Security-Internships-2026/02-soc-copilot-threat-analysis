"""
SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage
CNIT/PNTLab Pisa — AI Security Internship 2026

Entry point. Runs the alert-triage pipeline end to end:
  load data -> preprocess -> train/evaluate baseline classifier

By default this runs against the local synthetic sample
(datasets/sample/guide_sample.csv). Once the real GUIDE dataset is
downloaded (see datasets/README.md), it's picked up automatically.

See docs/proposal.md for research objectives and architecture.
"""

import argparse
import sys
from pathlib import Path

# Allow `python src/main.py` (per README) as well as `python -m src.main`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.baseline import (
    DEFAULT_MAX_ROWS,
    MODEL_PATH,
    expected_metadata,
    load_reusable_artifact,
    train_and_evaluate,
)

PROJECT_NAME = "SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage"
ORGANISATION = "CNIT/PNTLab Pisa, TECIP, Scuola Superiore Sant'Anna"
STATUS = "Week 17 — RF assigns every verdict, LLM explains only (see docs/weekly-progress.md)"


def main() -> None:
    parser = argparse.ArgumentParser(description=PROJECT_NAME)
    parser.add_argument(
        "--retrain",
        action="store_true",
        help="retrain the baseline even if a compatible saved artifact exists "
             "(overwrites experiments/results/baseline_model.joblib and baseline_metrics.json)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"Project : {PROJECT_NAME}")
    print(f"Org     : {ORGANISATION}")
    print(f"Status  : {STATUS}")
    print("=" * 60)
    print()

    # Never overwrite the deployed artifact without being asked to.
    #
    # This entry point is what the README's "Getting Started" tells a new
    # contributor to run, and until Week 17 it called train_and_evaluate()
    # unconditionally -- which atomically replaces baseline_model.joblib and
    # baseline_metrics.json. Every committed result in experiments/results/ is
    # scored by that exact artifact, so following the README destroyed the
    # provenance of the whole results directory.
    #
    # Three cases, and only one of them trains:
    #
    #   artifact reusable      -> reuse it, touch nothing
    #   artifact exists but
    #     metadata mismatched  -> STOP and explain. This is the important case:
    #                            load_reusable_artifact() hashes the whole of
    #                            src/data/schema.py and src/data/preprocess.py,
    #                            so an unrelated edit to either -- a new constant,
    #                            a comment -- reports "inputs changed" even when
    #                            the feature set is identical. Retraining on that
    #                            signal would silently move every published number.
    #   no artifact at all     -> train, because there is nothing to destroy
    metadata = expected_metadata(DEFAULT_MAX_ROWS, 0.2, 42)
    artifact = None if args.retrain else load_reusable_artifact(metadata)

    if artifact is not None:
        print("Reused the saved baseline; no training or full dataset load was needed.")
        print("Pass --retrain to force a fresh model.")
        return

    if args.retrain:
        print("--retrain given: training a fresh model and replacing the saved artifact.")
        train_and_evaluate(max_rows=DEFAULT_MAX_ROWS)
        return

    if MODEL_PATH.exists():
        print()
        print("=" * 72)
        print(" REFUSING TO RETRAIN")
        print("=" * 72)
        print(f" A saved baseline exists at {MODEL_PATH}, but its recorded inputs do")
        print(" not match the current ones (see the reason printed above).")
        print()
        print(" Retraining would replace it, and every result in experiments/results/")
        print(" is scored by that exact artifact -- so the committed figures and the")
        print(" model on disk would no longer correspond.")
        print()
        print(" If the mismatch is an unrelated edit to schema.py or preprocess.py,")
        print(" the saved model is still the right one and you want to keep it.")
        print(" If you genuinely intend to retrain, run:")
        print()
        print("     python src/main.py --retrain")
        print()
        print(" and then regenerate every downstream result.")
        print("=" * 72)
        raise SystemExit(1)

    print("No saved baseline found; training one.")
    train_and_evaluate(max_rows=DEFAULT_MAX_ROWS)


if __name__ == "__main__":
    main()
