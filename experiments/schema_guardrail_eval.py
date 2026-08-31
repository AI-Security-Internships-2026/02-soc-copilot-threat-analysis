# experiments/schema_guardrail_eval.py
#
# Regenerates the schema guardrail's headline evaluation artifact.
#
# Why this exists: the journal draft cites
# experiments/results/schema_guardrail_eval.json for both halves of the schema
# guardrail's claim -- 100% separation on the balanced synthetic set, and zero
# false positives on real AlertTitle values. That file was produced on a branch
# that never reached `dev` (issue #16 item E1 was marked done on the strength of
# a merge into an already-merged branch), so the paper has been citing an
# artifact no reader could reproduce from the repository. This script rebuilds
# it from committed inputs.
#
# The real-data half is the one that matters. The synthetic half is true by
# construction -- the check flags anything that is not int-parseable, so any 20
# non-numeric strings score 100% -- and is reported here with that caveat
# attached rather than as evidence of a clever detector.
#
# usage (from repo root):
#   venv/bin/python experiments/schema_guardrail_eval.py

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.agent.schema_guardrail import validate_field_types

CORPUS_PATH = Path("experiments/soc_domain_eval_v1.csv")
GUIDE_PATH = Path("datasets/GUIDE_train.csv")
OUTPUT_PATH = Path("experiments/results/schema_guardrail_eval.json")
N_REAL_SAMPLE = 5_000


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def main() -> None:
    with open(CORPUS_PATH) as handle:
        rows = list(csv.DictReader(handle))
    injections = [r["text"] for r in rows if r["label"] == "injection"]

    # Synthetic half: 20 numeric ids that must pass, 20 injection strings that
    # must be rejected.
    benign_ids = [str(i) for i in range(1, 21)]
    false_positives = [v for v in benign_ids if validate_field_types({"AlertTitle": v})]
    true_positives = [v for v in injections if validate_field_types({"AlertTitle": v})]
    synthetic_accuracy = (
        (len(benign_ids) - len(false_positives)) + len(true_positives)
    ) / (len(benign_ids) + len(injections))

    # Real-data half: the first N AlertTitle values in file order. Row order,
    # not a random sample -- stated plainly, because "no false positives in the
    # first 5,000 rows encountered" is a weaker claim than one about the full
    # 86,149-value population, and should not be dressed up as the latter.
    print(f"reading {N_REAL_SAMPLE} real AlertTitle values...")
    real = pd.read_csv(GUIDE_PATH, usecols=["AlertTitle"], nrows=N_REAL_SAMPLE)
    real_values = real["AlertTitle"].dropna().tolist()
    real_false_positives = [
        v for v in real_values if validate_field_types({"AlertTitle": v})
    ]

    output = {
        "experiment": "deterministic schema guardrail evaluation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "guardrail": "src/agent/schema_guardrail.py: AlertTitle/DetectorId must parse as integers",
        "synthetic": {
            "n_benign_numeric_ids": len(benign_ids),
            "n_injection_strings": len(injections),
            "false_positives": len(false_positives),
            "true_positives": len(true_positives),
            "accuracy": round(synthetic_accuracy, 4),
            "caveat": (
                "True by construction, not by discrimination. The check rejects "
                "anything that is not int-parseable, so any set of non-numeric "
                "strings scores 100% and any set of integers scores 0% false "
                "positives. This confirms the implementation matches its "
                "specification; it is not evidence that the guardrail "
                "recognises attacks."
            ),
        },
        "real_data": {
            "source": str(GUIDE_PATH),
            "n_sampled": len(real_values),
            "sampling": "first N rows in file order, not a random sample",
            "n_false_positives": len(real_false_positives),
            "false_positive_rate": round(len(real_false_positives) / len(real_values), 6),
            "claim_scope": (
                "No false positives among the first 5,000 AlertTitle values "
                "encountered. This is not a claim about the full 86,149-value "
                "population."
            ),
        },
        "status": "ran",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("=" * 60)
    print("SCHEMA GUARDRAIL EVALUATION")
    print("=" * 60)
    print(f"  synthetic : {synthetic_accuracy:.1%} accuracy "
          f"({len(false_positives)} FP, {len(injections) - len(true_positives)} FN)")
    print(f"              (true by construction -- see caveat in the JSON)")
    print(f"  real data : {len(real_false_positives)}/{len(real_values)} false positives "
          f"on AlertTitle values in file order")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
