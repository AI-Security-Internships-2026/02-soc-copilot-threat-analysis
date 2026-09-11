# experiments/kaggle_repro/kaggle_notebook_2.py
#
# M2.2 (issue #32), notebook 2 of 2.
#
# Ported from "94%ROC-RandomForest" by Mohamed Amr992
# (kaggle.com/code/mohamedamr992/94-roc-randomforest), 16 votes.
#
# This was NOT the second-highest-voted notebook on the dataset --
# safreita/incident-triage-prediction (26 votes) was -- but that notebook
# trains directly on GUIDE_Train.csv and scores on GUIDE_Test.csv with no
# `train_test_split` call anywhere in it (confirmed by reading the pulled
# .ipynb), so there is no row-level split in it to patch to GroupShuffleSplit
# and no (a)-vs-(b) delta to report. alexandrepedrosai/majorana-hardware
# (21 votes) was checked next and is unrelated to this dataset entirely
# (no GUIDE/IncidentGrade reference in its code -- a vote-count/dataset-tag
# mismatch, not a real candidate). This notebook is the next-highest-voted
# one that actually performs a row-level split, which is the real
# constraint the issue's comparison needs, not strictly vote rank.
#
# What was ported faithfully: the target definition (binarize IncidentGrade
# to TruePositive=1 vs rest=0), `RandomForestClassifier(class_weight=
# 'balanced', random_state=42)`, frequency-encoding of the high-cardinality
# categorical columns (the original's `df[col].value_counts(normalize=True)`
# pattern), and the original's own
# `train_test_split(test_size=0.2, random_state=42, stratify=y)`.
#
# What was simplified: the original reads the full ~9.5M-row GUIDE_train.csv
# with no nrows cap, then runs a 3-fold GridSearchCV over
# n_estimators in {300, 600, 750} scored on ROC-AUC -- a full day of CPU on
# this dataset size, not something this session's shared compute budget can
# afford twice (once per split rule) alongside the rest of M2/M3. A fixed
# RandomForestClassifier(n_estimators=300) on the same 300,000-row cap used
# for notebook 1 is used instead; the row cap is the deviation to flag, not
# the estimator choice (300 trees was inside the original's own search grid).
# The MITRE-technique multi-label one-hot expansion and the smoothed
# per-AlertTitle risk feature are dropped for the same reason -- neither
# changes which rows a row-level split can leak across.
#
# usage (from repo root):
#   venv/bin/python experiments/kaggle_repro/kaggle_notebook_2.py

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

TRAIN_DATA_PATH = Path("datasets/GUIDE_train.csv")
NROWS = 300_000
TEST_SIZE = 0.2
RANDOM_STATE = 42

FREQ_ENCODE_COLS = [
    "ThreatFamily",
    "AntispamDirection",
    "ActionGranular",
    "LastVerdict",
    "ResourceType",
    "Roles",
    "ActionGrouped",
    "EntityType",
    "Category",
    "SuspicionLevel",
    "EvidenceRole",
    "DetectorId",
    "AlertTitle",
    "OSFamily",
    "OSVersion",
]
DROP_COLS = [
    "Id",
    "OrgId",
    "IncidentId",
    "AlertId",
    "Timestamp",
    "Sha256",
    "DeviceId",
    "AccountSid",
    "AccountUpn",
    "AccountObjectId",
    "AccountName",
    "DeviceName",
    "NetworkMessageId",
    "RegistryValueName",
    "RegistryKey",
    "RegistryValueData",
    "ApplicationId",
    "ApplicationName",
    "OAuthApplicationId",
    "FileName",
    "FolderPath",
    "ResourceIdName",
    "EmailClusterId",
    "IncidentGrade",
    "MitreTechniques",
    "CountryCode",
    "State",
    "City",
    "IpAddress",
    "Url",
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
    for col in FREQ_ENCODE_COLS:
        if col in X.columns:
            X[col] = X[col].fillna("Missing")
            freq = X[col].value_counts(normalize=True)
            X[f"{col}_freq"] = X[col].map(freq)
            X = X.drop(columns=[col])
    X = X.select_dtypes(include=["number"]).fillna(-1)
    return X, y, groups


def fit_and_score(X_train, X_test, y_train, y_test) -> dict:
    model = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    return {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": round(accuracy_score(y_test, y_pred), 4),
        "f1_binary": round(f1_score(y_test, y_pred), 4),
        "roc_auc": round(roc_auc_score(y_test, y_proba), 4),
    }


def main() -> None:
    print("loading + preparing GUIDE_train.csv (nrows=300000)...")
    X, y, groups = load_and_prepare()
    print(f"rows: {len(X)}, positive rate: {y.mean():.4f}")

    print("\n(a) original row-level train_test_split(test_size=0.2, stratify=y)...")
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
        "experiment": (
            "M2.2 notebook 2/2: RandomForest, ported from "
            "kaggle.com/code/mohamedamr992/94-roc-randomforest"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "source_notebook": {
            "ref": "mohamedamr992/94-roc-randomforest",
            "title": "94%ROC-RandomForest",
            "author": "Mohamed Amr992",
            "total_votes_at_pull_time": 16,
            "url": "https://www.kaggle.com/code/mohamedamr992/94-roc-randomforest",
            "selection_note": (
                "Not the 2nd-highest vote count on the dataset -- the two "
                "higher-voted candidates were rejected for cause (see module "
                "docstring): one has no train_test_split to patch, one is "
                "unrelated to this dataset despite the vote-count tag match."
            ),
            "license_note": (
                "Notebook code is authored by Mohamed Amr992 and published on "
                "Kaggle; ported here for split-method comparison, attributed "
                "above, not redistributed verbatim."
            ),
        },
        "nrows": NROWS,
        "original_row_level_split": original,
        "groupshuffle_split": grouped,
        "delta_acc": delta_acc,
        "delta_f1_binary": round(original["f1_binary"] - grouped["f1_binary"], 4),
        "delta_roc_auc": round(original["roc_auc"] - grouped["roc_auc"], 4),
        "meets_ac_delta_ge_0_020": delta_acc >= 0.020,
    }

    out_path = Path("experiments/results/m2_2_kaggle_notebook_2.json")
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nsaved to {out_path}")
    print(f"delta_acc = {delta_acc}")


if __name__ == "__main__":
    main()
