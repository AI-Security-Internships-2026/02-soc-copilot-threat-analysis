# experiments/kaggle_repro/kaggle_notebook_1.py
#
# M2.2 (issue #32), notebook 1 of 2.
#
# Ported from "CatBoost" by Kuga Kugar (kaggle.com/code/kugakugar/catboost),
# 39 votes -- the highest-voted classification notebook found on the GUIDE
# dataset via the real Kaggle API (`kaggle kernels list --dataset
# Microsoft/microsoft-security-incident-prediction --sort-by voteCount`;
# credentials were available in ~/.kaggle/kaggle.json this session, so this
# is real vote-count-ranked selection, not the websearch fallback the
# original attempt recorded in this directory's README). No notebook on
# this dataset clears the issue's literal ">=50 upvotes" bar -- 39 is the
# real ceiling; documented here rather than silently claiming otherwise.
#
# What was ported faithfully: the target definition (binarize IncidentGrade
# to TruePositive=1 vs rest=0), the row cap (nrows=300_000, matching the
# original notebook's own `pd.read_csv(..., nrows=300000)`), CatBoost with
# native categorical-feature handling and `auto_class_weights='Balanced'`,
# and -- the part this experiment is actually about -- the original's
# `train_test_split(test_size=0.15, random_state=42, stratify=y)`.
#
# What was simplified: the original spends a 10-trial Optuna search
# (`study.optimize(objective, n_trials=10)`) tuning iterations/depth/
# learning_rate before its final fit. That search targets model quality,
# not split method, so it is orthogonal to the row-vs-group-split delta
# this script measures; fixed params close to the original's tuned result
# (depth=6, iterations=150, learning_rate=0.1) are used instead to keep
# this fast enough to run twice (once per split rule) in one session.
#
# usage (from repo root):
#   venv/bin/python experiments/kaggle_repro/kaggle_notebook_1.py

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

TRAIN_DATA_PATH = Path("datasets/GUIDE_train.csv")
NROWS = 300_000
TEST_SIZE = 0.15
RANDOM_STATE = 42

CAT_FEATURES = [
    "Category",
    "EntityType",
    "EvidenceRole",
    "OSFamily",
    "OSVersion",
    "AntispamDirection",
    "SuspicionLevel",
    "LastVerdict",
    "Roles",
    "ResourceType",
    "DetectorId",
    "AlertTitle",
]
DROP_COLS = [
    "Id",
    "OrgId",
    "IncidentId",
    "AlertId",
    "Timestamp",
    "ActionGrouped",
    "ActionGranular",
    "ThreatFamily",
    "MitreTechniques",
    "IncidentGrade",
]


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


def load_and_prepare() -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    df = pd.read_csv(TRAIN_DATA_PATH, nrows=NROWS)
    df = df.dropna(subset=["IncidentGrade"])
    y = (df["IncidentGrade"] == "TruePositive").astype(int)
    groups = df["OrgId"].astype(str) + "_" + df["IncidentId"].astype(str)
    X = df.drop(columns=[c for c in DROP_COLS if c in df.columns])
    for col in CAT_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna("Missing").astype(str)
    other_cols = [c for c in X.columns if c not in CAT_FEATURES]
    X[other_cols] = X[other_cols].fillna(-1)
    return X, y, groups


def fit_and_score(X_train, X_test, y_train, y_test) -> dict:
    cat_idx = [X_train.columns.get_loc(c) for c in CAT_FEATURES if c in X_train.columns]
    model = CatBoostClassifier(
        iterations=150,
        depth=6,
        learning_rate=0.1,
        auto_class_weights="Balanced",
        cat_features=cat_idx,
        verbose=False,
        random_state=RANDOM_STATE,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    return {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "f1_binary": round(f1_score(y_test, y_pred), 4),
    }


def main() -> None:
    print("loading + preparing GUIDE_train.csv (nrows=300000)...")
    X, y, groups = load_and_prepare()
    print(f"rows: {len(X)}, positive rate: {y.mean():.4f}")

    print("\n(a) original row-level train_test_split(test_size=0.15, stratify=y)...")
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    original = fit_and_score(X_tr, X_te, y_tr, y_te)
    print(json.dumps(original, indent=2))

    print("\n(b) patched GroupShuffleSplit(groups=OrgId+IncidentId)...")
    gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))
    X_tr2, X_te2 = X.iloc[train_idx], X.iloc[test_idx]
    y_tr2, y_te2 = y.iloc[train_idx], y.iloc[test_idx]
    crossing = len(set(groups.iloc[train_idx]) & set(groups.iloc[test_idx]))
    grouped = fit_and_score(X_tr2, X_te2, y_tr2, y_te2)
    grouped["incidents_crossing_boundary"] = crossing
    print(json.dumps(grouped, indent=2))

    delta_acc = round(original["accuracy"] - grouped["accuracy"], 4)
    result = {
        "experiment": "M2.2 notebook 1/2: CatBoost, ported from kaggle.com/code/kugakugar/catboost",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "source_notebook": {
            "ref": "kugakugar/catboost",
            "title": "CatBoost",
            "author": "Kuga Kugar",
            "total_votes_at_pull_time": 39,
            "url": "https://www.kaggle.com/code/kugakugar/catboost",
            "license_note": (
                "Notebook code is authored by Kuga Kugar and published on Kaggle; "
                "ported here for split-method comparison, attributed above, not "
                "redistributed verbatim."
            ),
        },
        "nrows": NROWS,
        "original_row_level_split": original,
        "groupshuffle_split": grouped,
        "delta_acc": delta_acc,
        "delta_f1_binary": round(original["f1_binary"] - grouped["f1_binary"], 4),
        "meets_ac_delta_ge_0_020": delta_acc >= 0.020,
    }

    out_path = Path("experiments/results/m2_2_kaggle_notebook_1.json")
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nsaved to {out_path}")
    print(f"delta_acc = {delta_acc}")


if __name__ == "__main__":
    main()
