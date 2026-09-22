# experiments/m3_1_interrater_kappa.py
#
# Issue #35 (M3.1). Computes the real Cohen's kappa between two independent
# human raters' completed copies of experiments/results/m3_1_rating_worksheet.csv.
#
# This script cannot manufacture its own input: a single rater labelling their
# own generated data isn't "independent" by construction, so the two
# --rater-a/--rater-b files this script reads have to come from two actual
# people. Until both exist, there is no kappa to report -- see
# docs/soc-injection-benchmark-datasheet.md's Annotation section, which
# states that plainly rather than filling in a number.
#
# usage (from repo root, once both rating passes are done):
#   venv/bin/python experiments/m3_1_interrater_kappa.py \
#       --rater-a path/to/rater_a_completed.csv \
#       --rater-b path/to/rater_b_completed.csv

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.metrics import cohen_kappa_score

KEY_PATH = Path("experiments/results/.m3_1_rating_worksheet_key.csv")
OUTPUT_PATH = Path("experiments/results/m3_1_interrater_kappa.json")

VALID_VERDICTS = {"injection", "benign"}


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def disagreement_distribution(
    key_rows: list[dict], disagreements: list[str]
) -> dict[str, dict]:
    """Spread the disagreeing rows across benign/F1-F7 (issue #35, supervisor
    request 2). The category is the benchmark_id prefix in the answer key --
    raters never see it, so this is a post-hoc breakdown only, and it can only
    ever redistribute disagreements that already happened, never change them."""
    by_category: dict[str, dict] = defaultdict(
        lambda: {"n_items": 0, "n_disagreements": 0, "worksheet_ids": []}
    )
    disagreed = set(disagreements)
    for row in key_rows:
        category = row["benchmark_id"].rsplit("_", 1)[0]
        bucket = by_category[category]
        bucket["n_items"] += 1
        if row["worksheet_id"] in disagreed:
            bucket["n_disagreements"] += 1
            bucket["worksheet_ids"].append(row["worksheet_id"])
    for bucket in by_category.values():
        bucket["disagreement_rate"] = round(bucket["n_disagreements"] / bucket["n_items"], 4)
    return dict(sorted(by_category.items()))


def _load_ratings(path: Path) -> dict[str, str]:
    with open(path) as handle:
        rows = list(csv.DictReader(handle))
    ratings = {}
    for row in rows:
        verdict = row["verdict"].strip().lower()
        if verdict not in VALID_VERDICTS:
            raise ValueError(
                f"{path}: worksheet_id={row['worksheet_id']} has verdict "
                f"{row['verdict']!r}, expected one of {sorted(VALID_VERDICTS)}"
            )
        ratings[row["worksheet_id"]] = verdict
    return ratings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rater-a", required=True, type=Path)
    parser.add_argument("--rater-b", required=True, type=Path)
    args = parser.parse_args()

    rater_a = _load_ratings(args.rater_a)
    rater_b = _load_ratings(args.rater_b)
    with open(KEY_PATH) as handle:
        key_rows = list(csv.DictReader(handle))

    missing_a = [r["worksheet_id"] for r in key_rows if r["worksheet_id"] not in rater_a]
    missing_b = [r["worksheet_id"] for r in key_rows if r["worksheet_id"] not in rater_b]
    if missing_a or missing_b:
        raise ValueError(
            f"incomplete ratings -- rater A missing {len(missing_a)}, "
            f"rater B missing {len(missing_b)} of {len(key_rows)} rows"
        )

    ids = [r["worksheet_id"] for r in key_rows]
    a_labels = [rater_a[i] for i in ids]
    b_labels = [rater_b[i] for i in ids]
    true_labels = [r["true_label"] for r in key_rows]

    kappa = float(cohen_kappa_score(a_labels, b_labels))
    disagreements = [i for i, a, b in zip(ids, a_labels, b_labels) if a != b]
    raw_agreement = (len(ids) - len(disagreements)) / len(ids)

    by_category = disagreement_distribution(key_rows, disagreements)
    a_accuracy = sum(1 for a, t in zip(a_labels, true_labels) if a == t) / len(ids)
    b_accuracy = sum(1 for b, t in zip(b_labels, true_labels) if b == t) / len(ids)
    n_attack = sum(1 for t in true_labels if t == "injection")
    n_benign = sum(1 for t in true_labels if t == "benign")

    output = {
        "experiment": "M3.1 interrater reliability (Cohen's kappa)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "n_rows": len(ids),
        "n_attack": n_attack,
        "n_benign": n_benign,
        "cohen_kappa": round(kappa, 4),
        "raw_agreement": round(raw_agreement, 4),
        "n_disagreements": len(disagreements),
        "disagreement_worksheet_ids": disagreements,
        "disagreement_distribution": by_category,
        "rater_a_accuracy_vs_true_label": round(a_accuracy, 4),
        "rater_b_accuracy_vs_true_label": round(b_accuracy, 4),
        "target": "kappa >= 0.75 (issue #35 acceptance criterion)",
        "meets_target": kappa >= 0.75,
        "rater_a_file": str(args.rater_a),
        "rater_b_file": str(args.rater_b),
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"Cohen's kappa: {kappa:.4f} (target >= 0.75, {'MET' if kappa >= 0.75 else 'NOT MET'})")
    print(f"raw agreement: {raw_agreement:.4f} ({len(disagreements)} disagreements of {len(ids)})")
    print("disagreements by category:")
    for category, bucket in by_category.items():
        print(
            f"  {category:<10} {bucket['n_disagreements']:>3}/{bucket['n_items']:<3} "
            f"({bucket['disagreement_rate']:.1%})"
        )
    print(f"saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
