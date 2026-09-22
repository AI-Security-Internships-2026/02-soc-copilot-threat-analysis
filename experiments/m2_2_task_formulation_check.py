"""
M2.2 follow-up -- does binary vs three-class formulation explain why our
split-method delta (~+0.030) is larger than the two Kaggle notebooks' (+0.0070,
+0.0092)?

Issue #32. The instruction is explicit that neither outcome is a target and that
no experiment should be tuned toward +0.020. Nothing here is tuned.

Design. Our published delta and the Kaggle ones differ in at least two ways at
once -- task formulation (3-class IncidentGrade vs binary TruePositive-vs-rest)
and sample size (100,000 vs 300,000 rows). Changing only the formulation would
leave sample size confounded, so this runs a 2x2:

        formulation x rows  ->  {three_class, binary} x {100k, 300k}

Each cell trains the identical RF-200 twice on the identical rows, varying only
the split rule (stratified row-level vs GroupShuffleSplit on the incident key),
and reports the accuracy delta between them. The binary arm uses the notebooks'
own target definition, `(IncidentGrade == "TruePositive")`, taken from
experiments/kaggle_repro/kaggle_notebook_1.py rather than invented here.

Reading the result, per the issue:
  (a) if the binary delta falls toward ~+0.007-0.009, formulation may explain it
  (b) if it stays near ~+0.030, formulation likely does not
  (c) either is acceptable

Run:  venv/bin/python experiments/m2_2_task_formulation_check.py
      venv/bin/python experiments/m2_2_task_formulation_check.py --rows 100000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.load_data import load_alerts
from src.data.preprocess import preprocess

OUT = Path("experiments/results/m2_2_task_formulation_check.json")
INCIDENT_KEY = ("OrgId", "IncidentId")
TEST_SIZE = 0.2
SEED = 42
N_TREES = 200


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def one_cell(X, y, groups, binary: bool) -> dict:
    """Train twice on identical rows, varying only the split rule."""
    idx = np.arange(len(X))
    tr_r, te_r = train_test_split(idx, test_size=TEST_SIZE, random_state=SEED, stratify=y)
    gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=SEED)
    tr_g, te_g = next(gss.split(X, y, groups=groups))

    arms = {}
    for name, (tr, te) in (("row_level", (tr_r, te_r)), ("group_level", (tr_g, te_g))):
        clf = RandomForestClassifier(n_estimators=N_TREES, random_state=SEED, n_jobs=-1)
        clf.fit(X.iloc[tr], y.iloc[tr])
        pred = clf.predict(X.iloc[te])
        truth = y.iloc[te]
        train_incidents = set(groups.iloc[tr])
        leaked = sum(1 for g in groups.iloc[te] if g in train_incidents)
        arms[name] = {
            "n_train": int(len(tr)), "n_test": int(len(te)),
            "accuracy": round(float(accuracy_score(truth, pred)), 4),
            "f1": round(float(f1_score(truth, pred,
                                       average="binary" if binary else "macro",
                                       zero_division=0)), 4),
            "holdout_rows_sharing_an_incident_with_train": int(leaked),
            "holdout_incident_leakage_rate": round(leaked / len(te), 4),
        }
    return {
        **arms,
        "delta_acc": round(arms["row_level"]["accuracy"] - arms["group_level"]["accuracy"], 4),
        "delta_f1": round(arms["row_level"]["f1"] - arms["group_level"]["f1"], 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, nargs="+", default=[100_000, 300_000])
    args = ap.parse_args()

    cells = {}
    for n_rows in args.rows:
        print(f"\nloading {n_rows:,} rows...", flush=True)
        raw = load_alerts(nrows=n_rows)
        keys = pd.Series(list(zip(raw[INCIDENT_KEY[0]], raw[INCIDENT_KEY[1]])),
                         index=raw.index)
        X, y3, _ = preprocess(raw)
        groups = keys.loc[X.index]
        # The notebooks' own target definition, not one invented here.
        y_bin = (y3.astype(str) == "TruePositive").astype(int)
        print(f"  {len(X):,} alerts, {X.shape[1]} features, {groups.nunique():,} incidents")
        print(f"  binary positive rate: {y_bin.mean():.4f}")

        for label, y in (("three_class", y3), ("binary", y_bin)):
            print(f"  running {label} @ {n_rows:,}...", flush=True)
            cells[f"{label}@{n_rows}"] = {
                "formulation": label, "rows": n_rows,
                "positive_rate": round(float(y_bin.mean()), 4) if label == "binary" else None,
                **one_cell(X, y, groups, binary=(label == "binary")),
            }

    # external comparators, read rather than retyped
    nb1 = json.loads(Path("experiments/results/m2_2_kaggle_notebook_1.json").read_text())
    nb2 = json.loads(Path("experiments/results/m2_2_kaggle_notebook_2.json").read_text())
    external = {
        "kaggle_notebook_1_catboost": {
            "delta_acc": nb1["delta_acc"], "rows": nb1["nrows"],
            "formulation": "binary (IncidentGrade == TruePositive)",
            "model": "CatBoost", "source": nb1["source_notebook"]["url"],
        },
        "kaggle_notebook_2_randomforest": {
            "delta_acc": nb2["delta_acc"], "rows": nb2["nrows"],
            "formulation": "binary (IncidentGrade == TruePositive)",
            "model": "RandomForest", "source": nb2["source_notebook"]["url"],
        },
    }

    ext_mean = float(np.mean([v["delta_acc"] for v in external.values()]))
    verdict = {}
    for n_rows in args.rows:
        three = cells[f"three_class@{n_rows}"]["delta_acc"]
        binv = cells[f"binary@{n_rows}"]["delta_acc"]
        # Does binarising move us most of the way to the external range?
        closes = abs(binv - ext_mean) < abs(three - ext_mean) * 0.5
        verdict[f"@{n_rows}"] = {
            "three_class_delta": three, "binary_delta": binv,
            "shift_from_binarising": round(binv - three, 4),
            "external_mean_delta": round(ext_mean, 4),
            "binary_delta_closes_most_of_the_gap": bool(closes),
            "reading": ("(a) formulation may explain part of the difference"
                        if closes else
                        "(b) formulation likely does NOT explain the difference"),
        }

    result = {
        "experiment": "M2.2 follow-up (issue #32) -- binary vs three-class as an "
                      "explanation for the split-method delta gap",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "design": "2x2, formulation x rows; each cell trains RF-200 twice on "
                  "identical rows varying only the split rule",
        "binary_target_definition": '(IncidentGrade == "TruePositive"), taken from '
                                    "experiments/kaggle_repro/kaggle_notebook_1.py",
        "no_tuning_note": "Per issue #32, no experiment was tuned toward +0.020 or "
                          "toward any target delta. Both outcomes were acceptable "
                          "in advance and the measured result is reported as-is.",
        "cells": cells,
        "external_comparators": external,
        "verdict": verdict,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    print("\n" + "=" * 68)
    print(f"  {'cell':24} {'delta_acc':>10} {'delta_f1':>9} {'leak(row)':>10}")
    for k, v in cells.items():
        print(f"  {k:24} {v['delta_acc']:>10.4f} {v['delta_f1']:>9.4f} "
              f"{v['row_level']['holdout_incident_leakage_rate']:>10.4f}")
    print(f"\n  external (binary, 300k): "
          f"{external['kaggle_notebook_1_catboost']['delta_acc']} (CatBoost), "
          f"{external['kaggle_notebook_2_randomforest']['delta_acc']} (RF)  "
          f"mean {ext_mean:.4f}")
    print("\n  verdict:")
    for k, v in verdict.items():
        print(f"    {k}: three-class {v['three_class_delta']} -> binary "
              f"{v['binary_delta']} ({v['shift_from_binarising']:+.4f})")
        print(f"        {v['reading']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
