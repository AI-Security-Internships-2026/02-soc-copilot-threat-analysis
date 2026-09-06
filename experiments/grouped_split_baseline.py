# experiments/grouped_split_baseline.py
#
# The Random Forest baseline the paper reports (Table 3: 0.7718 accuracy,
# 0.7505 macro F1, n_test=19,895) is produced by src/models/baseline.py
# using a plain stratified train_test_split:
#
#     X_train, X_test, y_train, y_test = train_test_split(
#         X, y, test_size=test_size, random_state=random_state, stratify=y
#     )
#
# That split is row-level. GUIDE rows are evidence records and the
# IncidentGrade label attaches to the incident, not the row (measured in
# experiments/incident_leakage_audit.py: the label is constant within an
# incident for effectively every incident in the training slice). So a
# row-level split puts sibling rows of one incident on both sides of the
# boundary, and the holdout score is partly a measure of whether the model
# can recall an incident it was shown rather than classify an alert it was
# not.
#
# This script quantifies how much that is worth, by running the same
# training twice on the same rows with the same hyperparameters, changing
# exactly one thing: the split rule.
#
#   ungrouped -- train_test_split, stratified. Reproduces the deployed
#                model's protocol, so the number it produces is directly
#                comparable to the published 0.7718.
#   grouped   -- GroupShuffleSplit on (OrgId, IncidentId). No incident
#                appears on both sides, so no holdout row has a labelled
#                sibling in training.
#
# Running both here, rather than comparing a new grouped number against the
# stored 0.7718, is deliberate: it holds sklearn version, feature encoding
# and row order fixed, so the difference between the two figures is
# attributable to the split rule and nothing else.
#
# Reading this beside incident_leakage_audit.py. That script reports a
# 24.3-point accuracy gap between leaked and clean rows; this one reports the
# published baseline is inflated by 2.8 points. The two are not in conflict --
# they answer different questions, and conflating them would overstate this
# result:
#
#   * the 24.3-point gap holds ONE model fixed and varies the row population,
#     on class-balanced buckets (majority-class floor 0.333). It measures how
#     much signal a shared incident carries.
#   * the 2.8-point gap varies the SPLIT RULE, which means the grouped arm is
#     retrained without those incidents and partly recovers by learning
#     features that generalise across them. Its holdout also follows GUIDE's
#     natural class distribution (majority floor ~0.45), so absolute accuracy
#     is not comparable to a balanced sample.
#
# The 2.8 points is the answer to "how inflated is the published baseline".
# The 24.3 points is the answer to "how potent is the leak for a fixed model".
#
# DIAGNOSTIC ONLY. This script does not write baseline_model.joblib and does
# not touch the deployed model. Every pipeline result in the repository was
# produced by the deployed model and remains valid; what changes is how the
# baseline's holdout score should be read.
#
# usage (from repo root):
#   venv/bin/python experiments/grouped_split_baseline.py

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
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from src.data.load_data import REAL_DATA_PATH, load_alerts
from src.data.preprocess import preprocess
from src.data.schema import TARGET_COLUMN
from src.models.baseline import DEFAULT_MAX_ROWS, TOTAL_TREES, TREE_BATCH_SIZE
from experiments.stats_utils import bootstrap_metric_ci, bootstrap_two_sample_diff_ci

INCIDENT_KEY = ["OrgId", "IncidentId"]
OUTPUT_PATH = Path("experiments/results/grouped_split_baseline.json")

PUBLISHED_UNGROUPED_ACCURACY = 0.7718
PUBLISHED_UNGROUPED_MACRO_F1 = 0.7505

SEED = 42
TEST_SIZE = 0.2


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def train_forest(X_train: pd.DataFrame, y_train: pd.Series, label: str) -> RandomForestClassifier:
    """Same estimator and warm-start schedule as src/models/baseline.py."""
    clf = RandomForestClassifier(
        n_estimators=0, random_state=SEED, n_jobs=-1, warm_start=True
    )
    for completed in range(0, TOTAL_TREES, TREE_BATCH_SIZE):
        clf.n_estimators = min(completed + TREE_BATCH_SIZE, TOTAL_TREES)
        clf.fit(X_train, y_train)
        print(f"  [{label}] trees {clf.n_estimators}/{TOTAL_TREES}", flush=True)
    return clf


def evaluate(clf, X_test, y_test, groups_test, train_incidents: set) -> dict:
    y_pred = clf.predict(X_test)
    y_true = list(y_test)
    y_pred = list(y_pred)

    shared = int(sum(g in train_incidents for g in groups_test))
    acc = lambda t, p: accuracy_score(t, p)
    macro_f1 = lambda t, p: f1_score(t, p, average="macro", zero_division=0)

    return {
        "n_test": len(y_true),
        "accuracy": round(acc(y_true, y_pred), 4),
        "accuracy_bootstrap_ci": bootstrap_metric_ci(y_true, y_pred, acc, seed=SEED),
        "macro_f1": round(macro_f1(y_true, y_pred), 4),
        "macro_f1_bootstrap_ci": bootstrap_metric_ci(y_true, y_pred, macro_f1, seed=SEED),
        "classification_report": classification_report(
            y_true, y_pred, zero_division=0, digits=3
        ),
        "holdout_rows_sharing_an_incident_with_train": shared,
        "holdout_incident_leakage_rate": round(shared / len(y_true), 4) if y_true else None,
        "_y_true": y_true,
        "_y_pred": y_pred,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quantify how much the RF baseline's holdout score depends "
        "on a row-level rather than incident-level split."
    )
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    args = parser.parse_args()

    if not REAL_DATA_PATH.exists():
        raise SystemExit(
            f"{REAL_DATA_PATH} not found. This diagnostic is about leakage in the "
            "real GUIDE data and is meaningless against the synthetic sample."
        )

    print(f"loading {args.max_rows:,} rows...", flush=True)
    raw = load_alerts(nrows=args.max_rows)

    # preprocess() drops ID_COLUMNS (including OrgId/IncidentId) and rows with
    # a missing target, so capture the grouping key first and realign it to
    # the surviving index afterwards.
    raw_keys = pd.Series(
        list(zip(raw[INCIDENT_KEY[0]], raw[INCIDENT_KEY[1]])), index=raw.index
    )
    X, y, _ = preprocess(raw)
    groups = raw_keys.loc[X.index]
    print(f"prepared {len(X):,} alerts, {X.shape[1]} features, "
          f"{groups.nunique():,} incidents", flush=True)

    # --- arm 1: the deployed protocol, row-level stratified split ---
    idx = np.arange(len(X))
    tr_i, te_i = train_test_split(
        idx, test_size=TEST_SIZE, random_state=SEED, stratify=y
    )
    ungrouped_train_incidents = set(groups.iloc[tr_i])
    print("\ntraining arm 1/2: ungrouped (row-level) split", flush=True)
    clf_u = train_forest(X.iloc[tr_i], y.iloc[tr_i], "ungrouped")
    ungrouped = evaluate(
        clf_u, X.iloc[te_i], y.iloc[te_i], list(groups.iloc[te_i]), ungrouped_train_incidents
    )

    # --- arm 2: incident-level split, no shared incidents ---
    gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=SEED)
    tr_g, te_g = next(gss.split(X, y, groups=groups))
    grouped_train_incidents = set(groups.iloc[tr_g])
    print("\ntraining arm 2/2: grouped (incident-level) split", flush=True)
    clf_g = train_forest(X.iloc[tr_g], y.iloc[tr_g], "grouped")
    grouped = evaluate(
        clf_g, X.iloc[te_g], y.iloc[te_g], list(groups.iloc[te_g]), grouped_train_incidents
    )

    # --- the difference the split rule is worth ---
    acc = lambda t, p: accuracy_score(t, p)
    macro_f1 = lambda t, p: f1_score(t, p, average="macro", zero_division=0)
    accuracy_gap = bootstrap_two_sample_diff_ci(
        ungrouped["_y_true"], ungrouped["_y_pred"],
        grouped["_y_true"], grouped["_y_pred"],
        acc, seed=SEED,
    )
    f1_gap = bootstrap_two_sample_diff_ci(
        ungrouped["_y_true"], ungrouped["_y_pred"],
        grouped["_y_true"], grouped["_y_pred"],
        macro_f1, seed=SEED,
    )

    for arm in (ungrouped, grouped):
        arm.pop("_y_true")
        arm.pop("_y_pred")

    output = {
        "experiment": (
            "RandomForest baseline trained twice on identical rows with identical "
            "hyperparameters, varying only the split rule: row-level stratified "
            "(the deployed protocol) vs incident-level GroupShuffleSplit"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "diagnostic_only": (
            "This script does NOT write baseline_model.joblib. The deployed model "
            "and every pipeline result derived from it are unchanged."
        ),
        "data_source": str(REAL_DATA_PATH),
        "max_rows": args.max_rows,
        "n_alerts_after_preprocess": int(len(X)),
        "n_features": int(X.shape[1]),
        "n_incidents": int(groups.nunique()),
        "split": {"test_size": TEST_SIZE, "random_state": SEED, "group_key": INCIDENT_KEY},
        "estimator": f"RandomForestClassifier(n_estimators={TOTAL_TREES}, random_state={SEED})",
        "published_reference": {
            "source": "experiments/results/baseline_metrics.json (Table 3)",
            "accuracy": PUBLISHED_UNGROUPED_ACCURACY,
            "macro_f1": PUBLISHED_UNGROUPED_MACRO_F1,
            "note": (
                "The ungrouped arm below re-runs that protocol here so both arms "
                "share a sklearn version and feature encoding; it should land "
                "close to this published figure."
            ),
        },
        "ungrouped_row_level_split": ungrouped,
        "grouped_incident_level_split": grouped,
        "accuracy_gap_ungrouped_minus_grouped": accuracy_gap,
        "macro_f1_gap_ungrouped_minus_grouped": f1_gap,
        "finding": (
            f"Holding data, features and hyperparameters fixed and changing only "
            f"the split rule, holdout accuracy moves from "
            f"{ungrouped['accuracy']} (row-level, "
            f"{ungrouped['holdout_incident_leakage_rate']:.1%} of holdout rows share "
            f"an incident with training) to {grouped['accuracy']} (incident-level, "
            f"{grouped['holdout_incident_leakage_rate']:.1%}). Difference "
            f"{accuracy_gap['point_diff']:+.4f}, 95% CI "
            f"[{accuracy_gap['ci_lower']:+.4f}, {accuracy_gap['ci_upper']:+.4f}] -- "
            + (
                "excludes 0, so the published baseline is inflated by the split rule "
                "by a measurable amount."
                if accuracy_gap["significant_at_confidence"]
                else "includes 0, so the split rule does not measurably inflate the "
                "published baseline at this sample size."
            )
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 72)
    print("GROUPED vs UNGROUPED BASELINE SPLIT")
    print("=" * 72)
    for name, arm in (("ungrouped (row-level)", ungrouped), ("grouped (incident)", grouped)):
        ci = arm["accuracy_bootstrap_ci"]
        print(f"  {name:24s} acc {arm['accuracy']} "
              f"[{ci['ci_lower']}, {ci['ci_upper']}]  macro F1 {arm['macro_f1']}  "
              f"n={arm['n_test']}  incident-leak {arm['holdout_incident_leakage_rate']:.1%}")
    print(f"\n  {output['finding']}")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
