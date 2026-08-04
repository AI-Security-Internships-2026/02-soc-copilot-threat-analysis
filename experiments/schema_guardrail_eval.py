"""
Scores src/agent/schema_guardrail.validate_field_types() against the same
20-benign/20-injection set used in tests/test_schema_guardrail.py, and (if
datasets/GUIDE_train.csv is present locally) against a real-data sample of
AlertTitle values -- and writes both results to a committed JSON file.

Why this script exists: PR #15 and docs/weekly-progress.md's Week 9 section
report "100% accuracy on 20v20 synthetic" and "0 false positives on 5,000
real AlertTitle values", but neither number lived anywhere as a reproducible,
committed artifact -- only as PR prose and a module docstring. This closes
that gap for the paper draft (docs/paper/draft.md, Evaluation item E1),
mirroring the pattern experiments/soc_domain_eval.py already established for
the Week 8 ML guardrail.

usage (run from repo root):
    venv/bin/python experiments/schema_guardrail_eval.py

Note: datasets/GUIDE_train.csv is gitignored (see .gitignore) and is not
present in every checkout. If it's missing, this script still runs the
synthetic 20v20 check and writes a results file, but the "real_data" section
of the output records that the check was skipped rather than fabricating a
result -- rerun this on a machine with the dataset present to fill it in.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.schema_guardrail import validate_field_types  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
INJECTION_STRINGS_PATH = REPO_ROOT / "experiments" / "soc_domain_eval_v1.csv"
GUIDE_TRAIN_PATH = REPO_ROOT / "datasets" / "GUIDE_train.csv"
RESULTS_PATH = REPO_ROOT / "experiments" / "results" / "schema_guardrail_eval.json"

# same 20 realistic numeric IDs as tests/test_schema_guardrail.py --
# kept in sync manually; if you change one, change the other.
REALISTIC_NUMERIC_IDS = [
    45654, 99614, 111349, 56759, 12345, 7, 999999, 100000, 1, 42,
    "45654", "12345", "7", "999999", "100000", 0, 8675309, 314159, 271828, 161803,
]

REAL_DATA_SAMPLE_SIZE = 5000


def load_injection_strings() -> list[str]:
    with open(INJECTION_STRINGS_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [row["text"] for row in rows if row["label"] == "injection"]


def run_synthetic_eval() -> dict:
    benign = REALISTIC_NUMERIC_IDS
    injection = load_injection_strings()
    assert len(benign) == 20, f"expected 20 benign IDs, got {len(benign)}"
    assert len(injection) == 20, f"expected 20 injection strings, got {len(injection)}"

    false_positives = [v for v in benign if validate_field_types({"AlertTitle": v})]
    false_negatives = [v for v in injection if not validate_field_types({"AlertTitle": v})]

    n = len(benign) + len(injection)
    correct = (len(benign) - len(false_positives)) + (len(injection) - len(false_negatives))

    return {
        "n_benign": len(benign),
        "n_injection": len(injection),
        "false_positives": [repr(v) for v in false_positives],
        "false_negatives": [repr(v) for v in false_negatives],
        "accuracy": round(correct / n, 4),
    }


def run_real_data_eval() -> dict:
    if not GUIDE_TRAIN_PATH.exists():
        return {
            "status": "skipped",
            "reason": (
                "datasets/GUIDE_train.csv not present in this checkout "
                "(gitignored, per .gitignore's datasets/**/*.csv rule). "
                "Rerun this script on a machine with the dataset downloaded "
                "to populate this section -- see datasets/README.md for source."
            ),
        }

    sampled_titles: list[str] = []
    with open(GUIDE_TRAIN_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sampled_titles.append(row["AlertTitle"])
            if len(sampled_titles) >= REAL_DATA_SAMPLE_SIZE:
                break

    false_positives = [
        v for v in sampled_titles if validate_field_types({"AlertTitle": v})
    ]

    return {
        "status": "ran",
        "source_file": str(GUIDE_TRAIN_PATH.relative_to(REPO_ROOT)),
        "n_sampled": len(sampled_titles),
        "n_false_positives": len(false_positives),
        "false_positive_examples": false_positives[:10],
    }


def main() -> None:
    synthetic = run_synthetic_eval()
    real_data = run_real_data_eval()

    print("synthetic 20v20 eval:")
    print(f"  accuracy: {synthetic['accuracy']}")
    print(f"  false positives: {synthetic['false_positives']}")
    print(f"  false negatives: {synthetic['false_negatives']}")
    print("\nreal-data eval:")
    print(f"  {real_data}")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "synthetic_20v20": synthetic,
            "real_data_sample": real_data,
        }, f, indent=2)
    print(f"\nresults written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
