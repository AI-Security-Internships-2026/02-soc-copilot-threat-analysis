# experiments/m2_1_historical_eval_overlap.py
#
# M2.1 PART C (issue #31). Table 14 (docs/final-report.md:615-616) already
# reports incident-level overlap for three evaluation sets:
#
#   999-alert train-sampled     1.40% exact-row / 55.76% incident-level
#   209-alert control subset    1.91% exact-row / 39.23% incident-level
#   GUIDE_Test n=999 sample     0.00% exact-row /  0.00% incident-level
#
# This script adds a fourth point -- the canonical 15,000-row GUIDE_Test
# held-out sample, which by construction has 0% overlap of either kind --
# and plots each set's incident-level overlap against its accuracy delta
# from the clean baseline (0.6998, the held-out figure Week 17 established
# as the only one worth quoting). If overlap and accuracy inflation move
# together across these four points, that is the visual closing argument
# tying split-method inflation (M2.1 PART A, +2.83pts) and incident-level
# leakage (M2.1 PART B, +24.3pts) to the same underlying mechanism.
#
# Overlap is computed fresh via experiments/overlap_audit.py's
# compute_overlap() against the same 100,000-row training slice every other
# M2.1 script uses -- not re-typed from Table 14. Accuracy for the two
# train-sampled points is CITED from their own established measurements
# (experiments/results/guide_test_holdout_eval.json), not recomputed here
# with a different code path that could silently diverge from the
# published figure. The two clean GUIDE_Test points are scored fresh with
# incident_leakage_audit.py's _score_rows() (same model, same tie-break)
# since neither has a previously-published accuracy of its own -- only
# their overlap is in Table 14.
#
# This script is not built to produce r >= 0.90 (the issue's stated
# expectation); it reports whatever the four points actually show,
# including if that turns out to be weaker or non-monotonic -- see the
# "confound" note in the interpretation if so.
#
# usage (from repo root):
#   venv/bin/python experiments/m2_1_historical_eval_overlap.py

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sklearn.metrics import accuracy_score

from experiments.incident_leakage_audit import _score_rows
from experiments.overlap_audit import compute_overlap, load_train_reference
from experiments.stats_utils import pearson_correlation
from src.agent.fallback_classifier import should_use_fallback

CACHE_DIR = Path("experiments/results/evaluation_samples")
OUTPUT_JSON_PATH = Path("experiments/results/m2_1_historical_eval_overlap.json")
OUTPUT_CSV_PATH = Path("experiments/results/m2_1_overlap_scatter.csv")

DEPLOYED_HELDOUT_ACCURACY = 0.6998  # experiments/results/guide_test_holdout_eval.json, n=15,000
EXPECTED_MIN_R = 0.90


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _fresh_accuracy(df: pd.DataFrame) -> float:
    y_true, y_pred = _score_rows(df)
    return float(accuracy_score(y_true, y_pred))


def main() -> None:
    print("loading the 100,000-row training reference for overlap...", flush=True)
    ref = load_train_reference()

    points = []

    # (a) 999 train-sampled -- accuracy CITED, overlap computed fresh
    path = CACHE_DIR / "guide_balanced_333_per_class_seed_42.csv"
    df = pd.read_csv(path)
    overlap = compute_overlap(df, ref)
    accuracy_cited = 0.7347  # guide_test_holdout_eval.json: train_sampled_999_rf_primary_pipeline
    points.append(
        {
            "name": "train_sampled_999",
            "path": str(path),
            "n": overlap["n"],
            "exact_row_overlap_pct": overlap["exact_row_overlap_pct"],
            "incident_level_overlap_pct": overlap["incident_level_overlap_pct"],
            "accuracy": accuracy_cited,
            "accuracy_source": "experiments/results/guide_test_holdout_eval.json:train_sampled_999_rf_primary_pipeline",
            "delta_vs_0_6998": round(accuracy_cited - DEPLOYED_HELDOUT_ACCURACY, 4),
        }
    )

    # (b) 209-alert control subset -- accuracy CITED, overlap computed fresh
    cache_999 = pd.read_csv(path)
    control_209 = cache_999[cache_999.apply(lambda r: not should_use_fallback(r.to_dict()), axis=1)]
    overlap = compute_overlap(control_209, ref)
    accuracy_cited = 0.6555  # experiments/results/rf_vs_llm_control.json:randomforest.accuracy
    points.append(
        {
            "name": "control_209",
            "path": str(path) + " (LLM-eligible subset, should_use_fallback()==False)",
            "n": overlap["n"],
            "exact_row_overlap_pct": overlap["exact_row_overlap_pct"],
            "incident_level_overlap_pct": overlap["incident_level_overlap_pct"],
            "accuracy": accuracy_cited,
            "accuracy_source": "experiments/results/rf_vs_llm_control.json:randomforest.accuracy",
            "delta_vs_0_6998": round(accuracy_cited - DEPLOYED_HELDOUT_ACCURACY, 4),
        }
    )

    # (c) GUIDE_Test n=999 sample -- clean, no prior accuracy citation exists; score fresh
    path = CACHE_DIR / "guide_test_balanced_333_per_class_seed_42.csv"
    df = pd.read_csv(path)
    overlap = compute_overlap(df, ref)
    print(f"scoring the {len(df)}-row GUIDE_Test n=999 sample fresh (no prior citation exists)...", flush=True)
    accuracy_fresh = _fresh_accuracy(df)
    points.append(
        {
            "name": "held_out_999",
            "path": str(path),
            "n": overlap["n"],
            "exact_row_overlap_pct": overlap["exact_row_overlap_pct"],
            "incident_level_overlap_pct": overlap["incident_level_overlap_pct"],
            "accuracy": round(accuracy_fresh, 4),
            "accuracy_source": "measured fresh by this script (_score_rows against baseline_model.joblib)",
            "delta_vs_0_6998": round(accuracy_fresh - DEPLOYED_HELDOUT_ACCURACY, 4),
        }
    )

    # (d) NEW: GUIDE_Test n=15,000 held-out -- the anchor itself, delta=0 by construction
    path = CACHE_DIR / "guide_test_balanced_5000_per_class_seed_42.csv"
    df = pd.read_csv(path)
    overlap = compute_overlap(df, ref)
    points.append(
        {
            "name": "held_out_15000",
            "path": str(path),
            "n": overlap["n"],
            "exact_row_overlap_pct": overlap["exact_row_overlap_pct"],
            "incident_level_overlap_pct": overlap["incident_level_overlap_pct"],
            "accuracy": DEPLOYED_HELDOUT_ACCURACY,
            "accuracy_source": "experiments/results/guide_test_holdout_eval.json:test_holdout_15000 (the anchor)",
            "delta_vs_0_6998": 0.0,
        }
    )

    x = [p["incident_level_overlap_pct"] for p in points]
    y = [p["delta_vs_0_6998"] for p in points]
    pearson = pearson_correlation(x, y)
    meets_expectation = pearson["r"] >= EXPECTED_MIN_R

    interpretation = (
        f"Across the 4 evaluation sets, Pearson r={pearson['r']:.4f} (p={pearson['p_value']:.4f}, n=4) "
        f"between incident-level overlap and accuracy delta from the clean 0.6998 baseline. "
        + (
            f"This meets the issue's r>=0.90 expectation: overlap and accuracy inflation move "
            f"together across these four points, closing the contamination-provenance picture."
            if meets_expectation
            else "This does NOT meet the issue's r>=0.90 expectation. With n=4, one point can move r a "
            "great deal; the control_209 point in particular is confounded -- Week 12 established "
            "that the LLM-eligible subset (evidence_field_count>=2) is intrinsically harder for the "
            "RF to classify than a typical alert, independent of contamination, so its accuracy "
            "delta reflects subset difficulty and contamination together, not contamination alone. "
            "Reported as measured rather than adjusted to fit the expectation."
        )
    )

    output = {
        "experiment": (
            "4-point scatter of incident-level training overlap vs accuracy delta from the clean "
            "0.6998 held-out baseline, across the evaluation sets this project reports on"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "protocol": "PREFERRED for (c)/(d); (a)/(b) are Protocol C/LAB_INFLATED comparators cited for the scatter",
        "deployed_heldout_accuracy_anchor": DEPLOYED_HELDOUT_ACCURACY,
        "points": points,
        "pearson_incident_overlap_vs_delta": pearson,
        "expected_min_r": EXPECTED_MIN_R,
        "meets_expected_min_r": meets_expectation,
        "interpretation": interpretation,
    }
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(output, indent=2))

    with OUTPUT_CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "name", "n", "exact_row_overlap_pct", "incident_level_overlap_pct",
                "accuracy", "delta_vs_0_6998",
            ],
        )
        writer.writeheader()
        for p in points:
            writer.writerow({k: p[k] for k in writer.fieldnames})

    print("\n" + "=" * 72)
    print("OVERLAP-VS-INFLATION SCATTER (M2.1 PART C)")
    print("=" * 72)
    for p in points:
        print(
            f"  {p['name']:20s} incident_overlap={p['incident_level_overlap_pct']:6.2f}%  "
            f"accuracy={p['accuracy']:.4f}  delta={p['delta_vs_0_6998']:+.4f}"
        )
    print(f"\n{interpretation}")
    print(f"\nsaved to {OUTPUT_JSON_PATH}")
    print(f"saved to {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()
