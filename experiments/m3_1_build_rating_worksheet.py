# experiments/m3_1_build_rating_worksheet.py
#
# Issue #35 (M3.1). Builds the blinded 100-row (50 attack / 50 benign)
# worksheet two independent human raters use to compute Cohen's kappa, and
# the answer key used to score their completed files.
#
# The worksheet deliberately drops every column that would give the answer
# away (family, is_benign_control, benchmark_id) -- only an opaque
# worksheet_id and the text a rater would actually see survive. The key
# lives in a separate, dot-prefixed file (not distributed to raters) so it
# can be committed for reproducibility without handing out the answers.
#
# usage (from repo root, after m3_1_generate_benchmark.py has run):
#   venv/bin/python experiments/m3_1_build_rating_worksheet.py

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

BENCHMARK_CSV = Path("datasets/soc_injection_benchmark_v1.csv")
WORKSHEET_PATH = Path("experiments/results/m3_1_rating_worksheet.csv")
KEY_PATH = Path("experiments/results/.m3_1_rating_worksheet_key.csv")

SUBSET_SIZE = 100
SEED = 42


def _scoring_text(row: dict) -> str:
    """Same one-line rule every M3.2 detector script uses: score the
    injected payload when present, else the real sampled alert text."""
    return row["injected_payload"] or row["original_value_snippet"]


def main() -> None:
    with open(BENCHMARK_CSV) as handle:
        rows = list(csv.DictReader(handle))

    attacks = [r for r in rows if r["is_benign_control"] == "False"]
    benign = [r for r in rows if r["is_benign_control"] == "True"]

    rng = np.random.default_rng(SEED)
    attack_sample = list(rng.choice(attacks, size=50, replace=False))
    benign_sample = list(rng.choice(benign, size=50, replace=False))
    subset = attack_sample + benign_sample
    rng.shuffle(subset)

    worksheet_rows = []
    key_rows = []
    for idx, row in enumerate(subset, start=1):
        worksheet_id = f"W{idx:03d}"
        worksheet_rows.append({"worksheet_id": worksheet_id, "text_shown": _scoring_text(row)})
        key_rows.append(
            {
                "worksheet_id": worksheet_id,
                "benchmark_id": row["benchmark_id"],
                "true_label": "benign" if row["is_benign_control"] == "True" else "injection",
            }
        )

    WORKSHEET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WORKSHEET_PATH, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["worksheet_id", "text_shown", "verdict"])
        writer.writeheader()
        for row in worksheet_rows:
            writer.writerow({**row, "verdict": ""})

    with open(KEY_PATH, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["worksheet_id", "benchmark_id", "true_label"])
        writer.writeheader()
        writer.writerows(key_rows)

    print(f"saved {WORKSHEET_PATH} (100 rows, verdict column blank for raters to fill in)")
    print(f"saved {KEY_PATH} (answer key -- not for distribution to raters)")


if __name__ == "__main__":
    main()
