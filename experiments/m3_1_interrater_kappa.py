# experiments/m3_1_interrater_kappa.py
#
# Issue #35 (M3.1). Computes the real Cohen's kappa between two independent
# human raters' completed copies of experiments/results/m3_1_rating_worksheet.csv.
#
# This script cannot manufacture its own input: a single rater labelling their
# own generated data isn't "independent" by construction, so the two
# --rater-a/--rater-b files this script reads have to come from two actual
# people. Both passes came back on 26 Sep 2025 and are committed alongside
# this script; see docs/m3-1-kappa-results.md for the report and the
# disagreement resolution log built from this script's output.
#
# Three things are reported, not one. The pooled kappa is the pre-registered
# acceptance criterion (issue #35), but the benign controls and the attack
# payloads differ in surface form, so the pooled number has a ceiling that
# was written down before the pass ran. The per-stratum breakdown is emitted
# next to it so that ceiling can be read directly instead of being hidden
# inside the pooled statistic.
#
# usage (from repo root):
#   venv/bin/python experiments/m3_1_interrater_kappa.py \
#       --rater-a experiments/results/m3_1_rating_sheet_raterA_completed.csv \
#       --rater-b experiments/results/m3_1_rating_sheet_raterB_completed.csv

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
BENCHMARK_CSV = Path("datasets/soc_injection_benchmark_v1.csv")
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


def agreement(a_labels: list[str], b_labels: list[str]) -> dict[str, float | None]:
    """Raw agreement, chance agreement and kappa over one set of rows.

    p_e is reported alongside kappa because this benchmark's strata have very
    different marginals: pooled it sits near 0.5, but on the attack-only rows
    both raters say "injection" almost every time, which drives p_e high and
    deflates kappa regardless of how well they actually agree (the
    high-prevalence kappa paradox). Without p_e in the output, a low
    per-stratum kappa reads as poor agreement when it is really a thin
    margin over chance -- so raw agreement is the figure to quote there."""
    n = len(a_labels)
    observed = sum(1 for a, b in zip(a_labels, b_labels) if a == b) / n
    expected = sum(
        (a_labels.count(label) / n) * (b_labels.count(label) / n)
        for label in set(a_labels) | set(b_labels)
    )
    # Both raters unanimous on every row -> p_e == 1 and kappa is undefined
    # (0/0), which is exactly what happens on the benign controls here.
    kappa = None if expected >= 1.0 else float(cohen_kappa_score(a_labels, b_labels))
    return {
        "n": n,
        "raw_agreement": round(observed, 4),
        "chance_agreement_p_e": round(expected, 4),
        "cohen_kappa": None if kappa is None else round(kappa, 4),
    }


def resolution_log(
    key_rows: list[dict], disagreements: list[str], ratings: dict[str, dict[str, str]]
) -> list[dict]:
    """The 100-subset disagreement resolution log required by issue #35, task 6.

    The adjudicated label is the benchmark's construction ground truth -- the
    generator knows what it injected into which field. That is recorded
    explicitly as the basis, because it is *not* a third independent human
    opinion, and a reader comparing rater accuracies needs to know which of
    the two is being measured against what."""
    with open(BENCHMARK_CSV) as handle:
        benchmark = {row["benchmark_id"]: row for row in csv.DictReader(handle)}
    by_id = {row["worksheet_id"]: row for row in key_rows}

    log = []
    for worksheet_id in disagreements:
        key = by_id[worksheet_id]
        row = benchmark[key["benchmark_id"]]
        log.append(
            {
                "worksheet_id": worksheet_id,
                "benchmark_id": key["benchmark_id"],
                "family": row["family"],
                "modified_field": row["modified_field"],
                "text_shown": row["injected_payload"] or row["original_value_snippet"],
                "rater_a": ratings["A"][worksheet_id],
                "rater_b": ratings["B"][worksheet_id],
                "adjudicated_label": key["true_label"],
                "adjudication_basis": "construction key (not a third human rater)",
                "rater_corrected": "A" if ratings["A"][worksheet_id] != key["true_label"] else "B",
            }
        )
    return log


def _load_ratings(path: Path, expected_rater: str) -> dict[str, str]:
    with open(path) as handle:
        rows = list(csv.DictReader(handle))
    ratings = {}
    for row in rows:
        # The build script pre-fills `rater` so a returned sheet is
        # self-identifying; checking it here is what actually stops the two
        # passes being swapped on the command line.
        if row.get("rater", "").strip().upper() != expected_rater:
            raise ValueError(
                f"{path}: worksheet_id={row['worksheet_id']} is rater "
                f"{row.get('rater')!r}, but was passed as rater {expected_rater} "
                f"-- check the --rater-a/--rater-b arguments are not swapped"
            )
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

    rater_a = _load_ratings(args.rater_a, "A")
    rater_b = _load_ratings(args.rater_b, "B")
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

    # Per-stratum agreement. The rubric's ceiling caveat says the pooled
    # number is carried by the benign controls, whose text is bare numeric
    # GUIDE field codes while every attack row is natural language; splitting
    # the strata is how that claim gets checked rather than asserted.
    strata = {
        label: agreement(
            [a for a, t in zip(a_labels, true_labels) if t == label],
            [b for b, t in zip(b_labels, true_labels) if t == label],
        )
        for label in ("injection", "benign")
    }

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
        "chance_agreement_p_e": round(
            sum(
                (a_labels.count(label) / len(ids)) * (b_labels.count(label) / len(ids))
                for label in VALID_VERDICTS
            ),
            4,
        ),
        "n_disagreements": len(disagreements),
        "disagreement_worksheet_ids": disagreements,
        "disagreement_distribution": by_category,
        "agreement_by_stratum": strata,
        "resolution_log": resolution_log(
            key_rows, disagreements, {"A": rater_a, "B": rater_b}
        ),
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
    print("by stratum (the pooled kappa's ceiling, see the rubric's ceiling caveat):")
    for label, stat in strata.items():
        shown = "undefined (raters unanimous)" if stat["cohen_kappa"] is None else f"{stat['cohen_kappa']:.4f}"
        print(
            f"  {label:<10} n={stat['n']:<4} agreement={stat['raw_agreement']:.4f} "
            f"p_e={stat['chance_agreement_p_e']:.4f} kappa={shown}"
        )
    print("disagreements by category:")
    for category, bucket in by_category.items():
        print(
            f"  {category:<10} {bucket['n_disagreements']:>3}/{bucket['n_items']:<3} "
            f"({bucket['disagreement_rate']:.1%})"
        )
    print(f"saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
