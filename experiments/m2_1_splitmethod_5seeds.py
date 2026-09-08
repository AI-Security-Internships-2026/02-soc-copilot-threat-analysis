# experiments/m2_1_splitmethod_5seeds.py
#
# M2.1 PART A (issue #31). grouped_split_baseline.py already measured the
# row-vs-group split-method inflation at one seed: +0.0283 accuracy, 95% CI
# [+0.0199, +0.0368]. A single seed is a point estimate of a quantity that
# depends on which rows land in the holdout; this script repeats the exact
# same measurement -- same 100,000-row slice, same RF-200/LabelEncoder
# config, same test_size=0.2 -- across 5 GroupShuffleSplit seeds and reports
# whether the effect is a stable property of the split rule or an artifact
# of one particular split.
#
# Reuses grouped_split_baseline.py's train_forest() (identical warm-start
# schedule to the deployed trainer) and evaluate() (identical metrics,
# including the incident-leakage sanity check) rather than reimplementing
# them -- the two scripts measure the same quantity at different seed
# counts and should not be able to silently drift apart.
#
# usage (from repo root):
#   venv/bin/python experiments/m2_1_splitmethod_5seeds.py
#   venv/bin/python experiments/m2_1_splitmethod_5seeds.py --seeds 42,123,456,789,1001

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from experiments.grouped_split_baseline import evaluate, train_forest
from experiments.stats_utils import wilcoxon_signed_rank
from src.data.load_data import REAL_DATA_PATH, load_alerts
from src.data.preprocess import preprocess
from src.models.baseline import DEFAULT_MAX_ROWS

INCIDENT_KEY = ["OrgId", "IncidentId"]
OUTPUT_PATH = Path("experiments/results/m2_1_splitmethod_delta_5seeds.json")
DEFAULT_SEEDS = [42, 123, 456, 789, 1001]
TEST_SIZE = 0.2
PUBLISHED_SINGLE_SEED_DELTA = 0.0283
PUBLISHED_SINGLE_SEED_CI = (0.0199, 0.0368)
BOOTSTRAP_RESAMPLES = 10_000
CI_SEED = 42  # the bootstrap-of-5-deltas resampling seed, distinct from the split seeds


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def bootstrap_ci_of_mean(values: list, n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = CI_SEED) -> dict:
    """Percentile bootstrap CI on the mean of a small set of scalars.

    Distinct from stats_utils.bootstrap_metric_ci, which resamples paired
    (y_true, y_pred) *rows* through a metric function -- there are only 5
    deltas here (one per seed), not thousands of rows, so this resamples the
    5 numbers themselves with replacement.
    """
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n == 0:
        raise ValueError("bootstrap_ci_of_mean: empty sample")
    rng = np.random.default_rng(seed)
    means = np.array([arr[rng.integers(0, n, n)].mean() for _ in range(n_resamples)])
    lower, upper = np.quantile(means, [0.025, 0.975])
    return {
        "mean": round(float(arr.mean()), 4),
        "ci_lower": round(float(lower), 4),
        "ci_upper": round(float(upper), 4),
        "confidence": 0.95,
        "n": n,
        "n_resamples": n_resamples,
        "method": "percentile bootstrap on the mean of a small (n=seeds) sample of deltas",
    }


def run_one_seed(X: pd.DataFrame, y: pd.Series, groups: pd.Series, seed: int) -> dict:
    idx = np.arange(len(X))
    tr_i, te_i = train_test_split(idx, test_size=TEST_SIZE, random_state=seed, stratify=y)
    row_train_incidents = set(groups.iloc[tr_i])
    print(f"  seed={seed}: training row-level split arm...", flush=True)
    clf_row = train_forest(X.iloc[tr_i], y.iloc[tr_i], f"row-seed{seed}")
    row_result = evaluate(clf_row, X.iloc[te_i], y.iloc[te_i], list(groups.iloc[te_i]), row_train_incidents)

    gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=seed)
    tr_g, te_g = next(gss.split(X, y, groups=groups))
    group_train_incidents = set(groups.iloc[tr_g])
    print(f"  seed={seed}: training group-level split arm...", flush=True)
    clf_group = train_forest(X.iloc[tr_g], y.iloc[tr_g], f"group-seed{seed}")
    group_result = evaluate(
        clf_group, X.iloc[te_g], y.iloc[te_g], list(groups.iloc[te_g]), group_train_incidents
    )

    for arm in (row_result, group_result):
        arm.pop("_y_true", None)
        arm.pop("_y_pred", None)

    delta_acc = row_result["accuracy"] - group_result["accuracy"]
    delta_f1 = row_result["macro_f1"] - group_result["macro_f1"]
    return {
        "seed": seed,
        "row_level_split": row_result,
        "group_level_split": group_result,
        "delta_acc": round(delta_acc, 4),
        "delta_macro_f1": round(delta_f1, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="5-seed replication of the row-vs-group split-method accuracy delta "
        "(single-seed reference: +0.0283, 95% CI [+0.0199, +0.0368])."
    )
    parser.add_argument("--seeds", type=str, default=",".join(str(s) for s in DEFAULT_SEEDS))
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    args = parser.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]

    if not REAL_DATA_PATH.exists():
        raise SystemExit(f"{REAL_DATA_PATH} not found. This measurement needs the real GUIDE data.")

    print(f"loading {args.max_rows:,} rows (shared across all {len(seeds)} seeds)...", flush=True)
    raw = load_alerts(nrows=args.max_rows)
    raw_keys = pd.Series(list(zip(raw[INCIDENT_KEY[0]], raw[INCIDENT_KEY[1]])), index=raw.index)
    X, y, _ = preprocess(raw)
    groups = raw_keys.loc[X.index]
    print(f"prepared {len(X):,} alerts, {X.shape[1]} features, {groups.nunique():,} incidents", flush=True)

    per_seed = []
    for seed in seeds:
        print(f"\n--- seed {seed} ---", flush=True)
        per_seed.append(run_one_seed(X, y, groups, seed))

    deltas_acc = [r["delta_acc"] for r in per_seed]
    deltas_f1 = [r["delta_macro_f1"] for r in per_seed]

    acc_agg = bootstrap_ci_of_mean(deltas_acc)
    acc_agg["std"] = round(float(np.std(deltas_acc)), 4)
    f1_agg = bootstrap_ci_of_mean(deltas_f1)
    f1_agg["std"] = round(float(np.std(deltas_f1)), 4)

    wilcoxon_acc = wilcoxon_signed_rank(deltas_acc)
    wilcoxon_f1 = wilcoxon_signed_rank(deltas_f1)

    published_ci_overlap = not (
        acc_agg["ci_upper"] < PUBLISHED_SINGLE_SEED_CI[0] or acc_agg["ci_lower"] > PUBLISHED_SINGLE_SEED_CI[1]
    )
    mean_exceeds_threshold = acc_agg["mean"] > 0.020
    wilcoxon_significant = wilcoxon_acc["p_value"] < 0.05

    interpretation = (
        f"Across {len(seeds)} seeds, mean Delta_acc = {acc_agg['mean']:+.4f} "
        f"(std {acc_agg['std']:.4f}), 95% CI [{acc_agg['ci_lower']:+.4f}, {acc_agg['ci_upper']:+.4f}]. "
        f"Wilcoxon signed-rank p={wilcoxon_acc['p_value']:.4f} vs a median-0 null. "
        + (
            "Mean exceeds +0.020 and the sign is consistent enough for Wilcoxon to reach "
            "significance at this seed count; "
            if mean_exceeds_threshold and wilcoxon_significant
            else "The effect does not clear both the +0.020 mean threshold and Wilcoxon p<0.05 "
            "at this seed count; "
        )
        + (
            f"the multi-seed CI overlaps the paper's single-seed estimate "
            f"(+{PUBLISHED_SINGLE_SEED_DELTA}, CI {list(PUBLISHED_SINGLE_SEED_CI)}), so the single-seed "
            "figure is not an outlier of the split-seed distribution."
            if published_ci_overlap
            else f"the multi-seed CI does NOT overlap the paper's single-seed estimate "
            f"(+{PUBLISHED_SINGLE_SEED_DELTA}, CI {list(PUBLISHED_SINGLE_SEED_CI)}) -- the single-seed "
            "figure may not be representative of the split-seed distribution."
        )
    )

    output = {
        "experiment": (
            "5-seed replication of the row-level-vs-group-level split-method accuracy/F1 delta, "
            "identical 100,000-row slice and RF-200/LabelEncoder config as grouped_split_baseline.py"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "protocol": "ACCEPTABLE",  # GroupShuffleSplit arm is Protocol B; row-level arm is the paired Protocol C comparator
        "data_source": str(REAL_DATA_PATH),
        "max_rows": args.max_rows,
        "seeds": seeds,
        "estimator": "RandomForestClassifier(n_estimators=200, random_state=<per-seed>)",
        "published_single_seed_reference": {
            "delta_acc": PUBLISHED_SINGLE_SEED_DELTA,
            "ci": list(PUBLISHED_SINGLE_SEED_CI),
            "source": "experiments/results/grouped_split_baseline.json",
        },
        "per_seed": per_seed,
        "aggregate_delta_acc": acc_agg,
        "aggregate_delta_macro_f1": f1_agg,
        "wilcoxon_delta_acc_vs_zero": wilcoxon_acc,
        "wilcoxon_delta_macro_f1_vs_zero": wilcoxon_f1,
        "checks": {
            "mean_delta_acc_exceeds_0_020": mean_exceeds_threshold,
            "wilcoxon_p_below_0_05": wilcoxon_significant,
            "multi_seed_ci_overlaps_published_single_seed_ci": published_ci_overlap,
        },
        "interpretation": interpretation,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 72)
    print("5-SEED SPLIT-METHOD DELTA")
    print("=" * 72)
    for r in per_seed:
        print(f"  seed={r['seed']:<5} delta_acc={r['delta_acc']:+.4f}  delta_f1={r['delta_macro_f1']:+.4f}")
    print(f"\n{interpretation}")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
