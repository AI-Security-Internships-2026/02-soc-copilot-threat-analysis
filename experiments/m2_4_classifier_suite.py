# experiments/m2_4_classifier_suite.py
#
# Issue #34 (M2.4, M2 -- Classifiers/Leakage). The deployed baseline is one
# untuned RandomForestClassifier(200) trained on 1% of GUIDE_train.csv. Two
# questions this project has not answered with evidence:
#
#   - independent review §31: does LabelEncoder's arbitrary ordinal
#     numbering of categorical values (AlertTitle=3 < AlertTitle=9000, a
#     relationship that means nothing) actually hurt a tree ensemble, or is
#     the concern moot in practice? M3a (RF + LabelEncoder, the deployed
#     encoding) vs M3b (RF + one-hot/overflow-bucket, no ordinality) answers
#     this directly, same estimator, same data, same split.
#   - independent review §32: a Q1-grade baseline suite needs more than one
#     tree-ensemble family. M4/M5/M6 add XGBoost, LightGBM (native
#     categorical splits, not LabelEncoder), and CatBoost (same) so RF isn't
#     the suite's only tree-based opinion.
#
# Seven arms:
#   M1  Majority             DummyClassifier(most_frequent) -- the floor
#   M2  LogReg (L2)          imputed + scaled, linear baseline
#   M3a RF (LabelEncoder)    the deployed encoding, exactly
#   M3b RF (one-hot)         top-30-per-column one-hot + a single overflow
#                            bucket for the rest, instead of a multi-bucket
#                            feature hash. This still isolates the thing
#                            §31 asks about -- ordinal vs non-ordinal
#                            categorical encoding -- without adding
#                            hash-collision variance as a second confound.
#                            Documented deviation from "frequency hashing".
#   M4  XGBoost              n_estimators=300, max_depth=6
#   M5  LightGBM             native categorical splits (categorical_feature=)
#   M6  CatBoost             native categorical splits (cat_features=),
#                            default hyperparameters
#   M7  LLM-only             Llama family via Groq, quota-constrained --
#                            see run_m7() and its own module docstring block
#
# Two modes, both required by the issue:
#   validate  5 GroupShuffleSplit seeds on the shared 100,000-row slice
#             (the deployed model's own training slice) -- mean/std per model
#   heldout   fit once on the feasible training budget, score the cached
#             15,000-row GUIDE_Test.csv held-out sample (0% incident overlap,
#             Week 17) with 95% bootstrap CIs on every headline cell
#
# Compute-budget deviation, stated rather than glossed: the issue's prose
# implies training on "GUIDE_train" without a row cap. This machine's 8GB
# ceiling was already established by classifier_improvement_study.py (a
# fully-grown RF-200 needs ~5.6GB at 1M rows). Rather than let some model
# families scale further just because they're leaner (XGBoost/LightGBM/
# CatBoost all handle far more than 500K rows comfortably), every model in
# "heldout" mode is capped at HELDOUT_TRAIN_ROWS so the comparison is an
# apples-to-apples same-training-budget comparison, not an
# each-model-however-far-it-can-go comparison.
#
# usage (from repo root):
#   venv/bin/python experiments/m2_4_classifier_suite.py --mode validate
#   venv/bin/python experiments/m2_4_classifier_suite.py --mode heldout
#   venv/bin/python experiments/m2_4_classifier_suite.py --mode heldout --model_id M3a
#   venv/bin/python experiments/m2_4_classifier_suite.py --model_id M7 --mode heldout --daily-call-budget 250

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import recall_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

from experiments.classifier_improvement_study import (
    accuracy,
    load_holdout,
    macro_f1,
    score_holdout,
)
from experiments.rf_vs_llm_control import mcnemar
from experiments.stats_utils import bootstrap_auc_ci, bootstrap_metric_ci, cochrans_q
from experiments.streaming_encode import load_encoded
from src.data.schema import TARGET_CLASSES, TARGET_COLUMN
from src.models.decision import predict_labels

TRAIN_DATA_PATH = Path("datasets/GUIDE_train.csv")
OUTPUT_VALIDATE_PATH = Path("experiments/results/m2_4_validate_5seed.json")
OUTPUT_HELDOUT_PATH = Path("experiments/results/m2_4_heldout_n15k.json")
OUTPUT_SELECTION_PATH = Path("experiments/results/m2_4_best_model_selection.json")
OUTPUT_M7_PATH = Path("experiments/results/m2_4_m7_llm_only.json")
M7_CHECKPOINT_PATH = Path("experiments/results/.m2_4_m7_checkpoint.jsonl")
BEST_CLASSIFIER_LINK = Path("models/best_classifier.joblib")
GROUPED_CLASSIFIER_ARTIFACT = Path("models/best_grouped_classifier.joblib")
M7_TARGET_N = 500

SEED = 42
VALIDATE_SEEDS = [42, 123, 456, 789, 1001]
VALIDATE_ROWS = 100_000  # the deployed model's own training slice (M2.1 PART A shares this)
HELDOUT_TRAIN_ROWS = 500_000  # see the compute-budget note in the module docstring
TOP_K_ONEHOT = 30  # M3b: top categories per column kept as their own one-hot column

TABULAR_MODEL_IDS = ["M1", "M2", "M3a", "M3b", "M4", "M5", "M6"]
ALL_MODEL_IDS = TABULAR_MODEL_IDS + ["M7"]

# Every classes_ this script produces must agree on this order -- it's what
# src/models/decision.py's tie-break and every downstream comparison assumes.
Y_ENCODER = LabelEncoder()
Y_ENCODER.fit(TARGET_CLASSES)


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def fit_timed(estimator, X, y):
    t = time.time()
    estimator.fit(X, y)
    return estimator, round(time.time() - t, 1)


# ---------------------------------------------------------------- one-hot (M3b)


def build_onehot(X_label_encoded: pd.DataFrame, encoders: dict) -> tuple[pd.DataFrame, dict]:
    """Top-K one-hot + a single overflow bucket per categorical column.

    Built directly from the already label-encoded integer codes rather than
    re-reading raw strings: encoding is bijective, so code frequency equals
    raw-value frequency, and this avoids a second pass over the CSV.
    """
    cat_cols = list(encoders.keys())
    num_cols = [c for c in X_label_encoded.columns if c not in cat_cols]
    parts = [X_label_encoded[num_cols].reset_index(drop=True)]
    top_categories: dict[str, list[int]] = {}
    for col in cat_cols:
        top_codes = X_label_encoded[col].value_counts().head(TOP_K_ONEHOT).index.tolist()
        top_categories[col] = top_codes
        bucketed = X_label_encoded[col].where(X_label_encoded[col].isin(top_codes), other=-1)
        dummies = pd.get_dummies(bucketed, prefix=col)
        overflow_col = f"{col}_-1"
        if overflow_col not in dummies.columns:
            dummies[overflow_col] = 0
        parts.append(dummies.reset_index(drop=True))
    X_onehot = pd.concat(parts, axis=1)
    return X_onehot, top_categories


def apply_onehot(
    X_label_encoded: pd.DataFrame, encoders: dict, top_categories: dict, feature_names: list
) -> pd.DataFrame:
    """Apply a fitted top-K-plus-overflow scheme to already label-encoded rows."""
    cat_cols = list(encoders.keys())
    num_cols = [c for c in X_label_encoded.columns if c not in cat_cols]
    parts = [X_label_encoded[num_cols].reset_index(drop=True)]
    for col in cat_cols:
        top_codes = top_categories[col]
        bucketed = X_label_encoded[col].where(X_label_encoded[col].isin(top_codes), other=-1)
        dummies = pd.get_dummies(bucketed, prefix=col)
        overflow_col = f"{col}_-1"
        if overflow_col not in dummies.columns:
            dummies[overflow_col] = 0
        parts.append(dummies.reset_index(drop=True))
    X_onehot = pd.concat(parts, axis=1)
    return X_onehot.reindex(columns=feature_names, fill_value=0)


def score_holdout_onehot(
    model, encoders: dict, top_categories: dict, feature_names: list, holdout: pd.DataFrame
) -> dict:
    """M3b's own score_holdout: transform_with_encoders, then one-hot, then predict."""
    from src.data.preprocess import transform_with_encoders

    frame = holdout.copy()
    ts = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)
    frame["Hour"], frame["DayOfWeek"], frame["Month"] = ts.dt.hour, ts.dt.dayofweek, ts.dt.month
    X_label_encoded = transform_with_encoders(frame, encoders)
    X_onehot = apply_onehot(X_label_encoded, encoders, top_categories, feature_names)
    y = holdout[TARGET_COLUMN]
    pred = predict_labels(model, X_onehot)
    return {
        "n": int(len(y)),
        "accuracy": accuracy(y, pred),
        "macro_f1": macro_f1(y, pred),
        "per_class_recall": {
            label: float(recall_score(y, pred, labels=[label], average="macro", zero_division=0))
            for label in TARGET_CLASSES
        },
        "_y_true": list(y),
        "_y_pred": list(pred),
    }


# ---------------------------------------------------------------- model factories


def make_estimator(model_id: str, cat_cols: list[str]):
    """(estimator, kind) -- kind flags fit()-time handling this script needs."""
    if model_id == "M1":
        return DummyClassifier(strategy="most_frequent"), "plain"
    if model_id == "M2":
        # sklearn's LogisticRegression cannot take NaN; RF/boosted trees
        # handle it natively (streaming_encode.py's own rationale for
        # leaving numeric NaNs unfilled), so only this arm needs imputation.
        return (
            Pipeline(
                [
                    ("impute", SimpleImputer(strategy="median")),
                    ("scale", StandardScaler()),
                    ("clf", LogisticRegression(penalty="l2", max_iter=2000, random_state=SEED)),
                ]
            ),
            "plain",
        )
    if model_id in ("M3a", "M3b"):
        return RandomForestClassifier(n_estimators=200, random_state=SEED, n_jobs=-1), "plain"
    if model_id == "M4":
        return (
            XGBClassifier(
                n_estimators=300, max_depth=6, random_state=SEED, n_jobs=-1, eval_metric="mlogloss"
            ),
            "xgboost",
        )
    if model_id == "M5":
        return (
            LGBMClassifier(n_estimators=200, random_state=SEED, n_jobs=-1, verbosity=-1),
            "lightgbm",
        )
    if model_id == "M6":
        return CatBoostClassifier(random_state=SEED, verbose=False, thread_count=-1), "catboost"
    raise ValueError(f"no tabular factory for {model_id}")


class _ClassesOverride:
    """Wraps a fitted estimator whose own .classes_ is read-only/numeric.

    XGBoost 3.x's XGBClassifier.classes_ is a read-only property returning
    0..k-1 (its internal numeric label encoding), not this project's string
    labels, and cannot be assigned directly. Its predict_proba columns are
    still ordered by those same numeric labels, which -- because Y_ENCODER
    assigns codes in sorted order, the same convention every LabelEncoder in
    this project uses -- is exactly Y_ENCODER.classes_'s order. This wrapper
    substitutes a writable .classes_ so predict_labels()/resolve_labels()
    (src/models/decision.py) hand back the same string labels every other
    model in this suite does, rather than bare integers.
    """

    def __init__(self, estimator, classes):
        self._estimator = estimator
        self.classes_ = np.asarray(classes)
        if hasattr(estimator, "feature_names_in_"):
            self.feature_names_in_ = estimator.feature_names_in_

    def predict_proba(self, X):
        return self._estimator.predict_proba(X)


def fit_model(model_id: str, estimator, kind: str, X: pd.DataFrame, y: pd.Series, cat_cols: list[str]):
    if kind == "xgboost":
        fitted, seconds = fit_timed(estimator, X, Y_ENCODER.transform(y))
        return _ClassesOverride(fitted, Y_ENCODER.classes_), seconds
    if kind == "lightgbm":
        t = time.time()
        estimator.fit(X, y, categorical_feature=cat_cols)
        return estimator, round(time.time() - t, 1)
    if kind == "catboost":
        t = time.time()
        estimator.fit(X, y, cat_features=cat_cols)
        return estimator, round(time.time() - t, 1)
    return fit_timed(estimator, X, y)


# ---------------------------------------------------------------- mode: validate


def run_validate(model_ids: list[str]) -> dict:
    print(f"loading the {VALIDATE_ROWS:,}-row validate slice...", flush=True)
    X, y, groups, encoders = load_encoded(TRAIN_DATA_PATH, VALIDATE_ROWS)
    cat_cols = list(encoders.keys())

    onehot_needed = "M3b" in model_ids
    X_onehot, top_categories = (build_onehot(X, encoders) if onehot_needed else (None, None))

    per_model: dict[str, list[dict]] = {mid: [] for mid in model_ids}

    for seed in VALIDATE_SEEDS:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
        train_idx, test_idx = next(splitter.split(X, y, groups))
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        for model_id in model_ids:
            Xt = X_onehot if model_id == "M3b" else X
            X_train, X_test = Xt.iloc[train_idx], Xt.iloc[test_idx]

            estimator, kind = make_estimator(model_id, cat_cols)
            fitted, seconds = fit_model(model_id, estimator, kind, X_train, y_train, cat_cols)
            pred = predict_labels(fitted, X_test)

            proba = fitted.predict_proba(X_test)
            classes = list(fitted.classes_)
            auc = bootstrap_auc_ci(list(y_test), proba, classes=classes, n_resamples=500, seed=seed)

            per_class_recall = {
                label: float(recall_score(y_test, pred, labels=[label], average="macro", zero_division=0))
                for label in TARGET_CLASSES
            }
            per_model[model_id].append(
                {
                    "seed": seed,
                    "n_train": int(len(train_idx)),
                    "n_test": int(len(test_idx)),
                    "accuracy": accuracy(y_test, pred),
                    "macro_f1": macro_f1(y_test, pred),
                    "per_class_recall": per_class_recall,
                    "macro_auc": auc["point"],
                    "train_seconds": seconds,
                }
            )
            print(
                f"  seed={seed:<5} {model_id:<4} acc={per_model[model_id][-1]['accuracy']:.4f} "
                f"f1={per_model[model_id][-1]['macro_f1']:.4f} ({seconds}s)",
                flush=True,
            )

    summary = {}
    for model_id, runs in per_model.items():
        accs = np.array([r["accuracy"] for r in runs])
        f1s = np.array([r["macro_f1"] for r in runs])
        summary[model_id] = {
            "runs": runs,
            "accuracy_mean": round(float(accs.mean()), 4),
            "accuracy_std": round(float(accs.std()), 4),
            "macro_f1_mean": round(float(f1s.mean()), 4),
            "macro_f1_std": round(float(f1s.std()), 4),
        }

    return {
        "validate_rows": VALIDATE_ROWS,
        "seeds": VALIDATE_SEEDS,
        "split": "incident-level GroupShuffleSplit on (OrgId, IncidentId), test_size=0.2",
        "models": summary,
    }


# ---------------------------------------------------------------- mode: heldout


def run_heldout(model_ids: list[str]) -> dict:
    print(f"loading the {HELDOUT_TRAIN_ROWS:,}-row heldout training slice...", flush=True)
    X, y, groups, encoders = load_encoded(TRAIN_DATA_PATH, HELDOUT_TRAIN_ROWS)
    cat_cols = list(encoders.keys())
    feature_names = list(X.columns)

    onehot_needed = "M3b" in model_ids
    X_onehot, top_categories = (build_onehot(X, encoders) if onehot_needed else (None, None))
    onehot_feature_names = list(X_onehot.columns) if X_onehot is not None else None

    holdout = load_holdout()

    results = {}
    correct_by_model: dict[str, list[bool]] = {}
    y_true_ref = None

    for model_id in model_ids:
        print(f"fitting {model_id} on {HELDOUT_TRAIN_ROWS:,} rows...", flush=True)
        estimator, kind = make_estimator(model_id, cat_cols)
        Xt = X_onehot if model_id == "M3b" else X
        fitted, seconds = fit_model(model_id, estimator, kind, Xt, y, cat_cols)

        if model_id == "M3b":
            scored = score_holdout_onehot(fitted, encoders, top_categories, onehot_feature_names, holdout)
        else:
            scored = score_holdout(fitted, encoders, feature_names, holdout)

        y_true_ref = scored["_y_true"] if y_true_ref is None else y_true_ref
        correct_by_model[model_id] = [t == p for t, p in zip(scored["_y_true"], scored["_y_pred"])]

        acc_ci = bootstrap_metric_ci(scored["_y_true"], scored["_y_pred"], accuracy, seed=SEED)
        f1_ci = bootstrap_metric_ci(scored["_y_true"], scored["_y_pred"], macro_f1, seed=SEED)

        expected_names = onehot_feature_names if model_id == "M3b" else feature_names
        names_ok = (
            hasattr(fitted, "feature_names_in_") and list(fitted.feature_names_in_) == expected_names
        )
        results[model_id] = {
            "n": scored["n"],
            "accuracy": scored["accuracy"],
            "accuracy_bootstrap_ci": acc_ci,
            "macro_f1": scored["macro_f1"],
            "macro_f1_bootstrap_ci": f1_ci,
            "per_class_recall": scored["per_class_recall"],
            "train_seconds": seconds,
            "train_rows": HELDOUT_TRAIN_ROWS,
            **check_deploy_compatibility(model_id, names_ok),
        }
        print(
            f"  {model_id}: acc={scored['accuracy']:.4f} f1={scored['macro_f1']:.4f} ({seconds}s)",
            flush=True,
        )

    # ---- pairwise McNemar (only meaningful among rows scored by both) -----
    def mcnemar_pair(name_a: str, name_b: str) -> dict:
        if name_a not in correct_by_model or name_b not in correct_by_model:
            return {"status": f"{name_a} or {name_b} not run this call"}
        raw = mcnemar(correct_by_model[name_a], correct_by_model[name_b])
        a_wrong_b_right = raw["llm_correct_rf_wrong"]
        a_right_b_wrong = raw["rf_correct_llm_wrong"]
        odds_ratio = (
            a_right_b_wrong / a_wrong_b_right if a_wrong_b_right else float("inf")
        )
        return {
            "a": name_a,
            "b": name_b,
            "both_correct": raw["both_correct"],
            f"{name_a}_correct_{name_b}_wrong": raw["rf_correct_llm_wrong"],
            f"{name_b}_correct_{name_a}_wrong": raw["llm_correct_rf_wrong"],
            "both_wrong": raw["both_wrong"],
            "discordant_pairs": raw["discordant_pairs"],
            "p_value": raw["p_value"],
            # McNemar odds ratio = (a-right/b-wrong) / (a-wrong/b-right) among
            # discordant pairs -- >1 means a wins more of the disagreements.
            "odds_ratio_a_over_b": round(odds_ratio, 4) if odds_ratio != float("inf") else None,
        }

    mcnemar_pairs = {
        "M6_vs_M3a": mcnemar_pair("M6", "M3a"),
        "M3a_vs_M3b": mcnemar_pair("M3a", "M3b"),
        # M6_vs_M7 is added by run_m7() once the LLM arm has results, since M7
        # scores a different (smaller) row subset than the tabular models --
        # see combine_with_m7().
    }

    # ---- Cochran's Q across whichever tabular models M1-M6 were run -------
    tabular_run = [mid for mid in TABULAR_MODEL_IDS if mid in correct_by_model]
    cochran_result = None
    if len(tabular_run) >= 2:
        matrix = np.column_stack([np.array(correct_by_model[mid], dtype=float) for mid in tabular_run])
        cochran_result = cochrans_q(matrix)
        cochran_result["models"] = tabular_run

    interpretation = None
    if "M3a" in results and "M3b" in results:
        gap = results["M3a"]["accuracy"] - results["M3b"]["accuracy"]
        p = mcnemar_pairs["M3a_vs_M3b"].get("p_value")
        significant = p is not None and p < 0.05
        interpretation = (
            f"M3a (LabelEncoder, ordinal codes) scores {results['M3a']['accuracy']:.4f} accuracy "
            f"vs M3b (top-{TOP_K_ONEHOT}-plus-overflow one-hot, non-ordinal) at "
            f"{results['M3b']['accuracy']:.4f} -- a gap of {gap:+.4f}. McNemar p={p}. "
            + (
                "This is a real difference at the 5% level: LabelEncoder's arbitrary ordinal "
                "numbering measurably " + ("helps" if gap > 0 else "hurts") + " this RF, "
                "answering independent review §31 directly."
                if significant
                else "This does not clear the 5% significance level, so the LabelEncoder-vs-one-hot "
                "choice is not distinguishable from noise at this held-out sample size -- §31's "
                "ordinality concern is not supported as a material effect here."
            )
        )

    return {
        "heldout_train_rows": HELDOUT_TRAIN_ROWS,
        "holdout_sample_n": len(y_true_ref) if y_true_ref else None,
        "models": results,
        "mcnemar_pairs": mcnemar_pairs,
        "cochrans_q_tabular_m1_m6": cochran_result,
        "m3a_vs_m3b_interpretation": interpretation,
        "_correct_by_model": correct_by_model,  # consumed by run_m7()/main(), stripped before saving
    }


# ---------------------------------------------------------------- selection rule


def select_best(heldout_models: dict, correct_by_model: dict[str, list[bool]]) -> dict:
    """best beats second-best by >1.5 acc pts AND McNemar p<0.05 -> best; else RF.

    McNemar is computed directly for whichever pair actually turns out to be
    best-vs-second-best -- not looked up among the three pairs the issue asks
    to have reported separately (M6-M3a, M6-M7, M3a-M3b), because the best
    model is frequently neither M6 nor M3a (M5 won in the smoke test that
    caught this). Reusing only the fixed three would silently fall back to
    RF on every run where the winner wasn't one of them, regardless of
    whether the actual winner was significant.
    """
    ranked = sorted(
        ((mid, m["accuracy"]) for mid, m in heldout_models.items() if mid != "M1"),
        key=lambda pair: pair[1],
        reverse=True,
    )
    if len(ranked) < 2:
        return {"rule": "insufficient models run", "selected": None}

    best_id, best_acc = ranked[0]
    second_id, second_acc = ranked[1]
    gap_pts = (best_acc - second_acc) * 100

    mcnemar_result = None
    if best_id in correct_by_model and second_id in correct_by_model:
        raw = mcnemar(correct_by_model[best_id], correct_by_model[second_id])
        mcnemar_result = {
            "a": best_id,
            "b": second_id,
            "both_correct": raw["both_correct"],
            f"{best_id}_correct_{second_id}_wrong": raw["rf_correct_llm_wrong"],
            f"{second_id}_correct_{best_id}_wrong": raw["llm_correct_rf_wrong"],
            "both_wrong": raw["both_wrong"],
            "discordant_pairs": raw["discordant_pairs"],
            "p_value": raw["p_value"],
        }

    return {
        "rule": "best beats second-best by >1.5 accuracy points AND McNemar p<0.05 -> select best; else select RF (M3a)",
        "ranked": ranked,
        "best_candidate": best_id,
        "second_best": second_id,
        "gap_accuracy_points": round(gap_pts, 4),
        "gap_exceeds_1_5_points": gap_pts > 1.5,
        "mcnemar_best_vs_second": mcnemar_result,
    }


# ---------------------------------------------------------------- deployment compatibility


def check_deploy_compatibility(model_id: str, feature_names_in_ok: bool) -> dict:
    """Does the deployed single-alert inference path.

    accept this estimator if M2.3 chooses to deploy it?
    fallback_classifier.py raises if the loaded estimator lacks
    feature_names_in_. sklearn RF/LogReg and XGBoost/LightGBM (fit on a
    DataFrame) set it automatically; CatBoost does not use that attribute
    name. This just records the fact M2.3 will need; the M3a-selection ->
    models/best_classifier.joblib link is written at the end of main(),
    pointing at M2.3's models/best_grouped_classifier.joblib artifact since
    both scripts train the identical procedure (500K rows, GroupShuffleSplit)
    and report the same 0.7294 heldout accuracy for M3a.
    """
    if feature_names_in_ok:
        return {"deploy_compatible": True}
    return {
        "deploy_compatible": False,
        "reason": (
            f"{model_id}'s estimator does not set feature_names_in_ the way "
            "fallback_classifier.py's single-alert inference path requires "
            "(known gap: CatBoost). If M2.3 chooses this model for deployment, "
            "it needs a compatibility wrapper first."
        ),
    }


# ---------------------------------------------------------------- M7 (LLM-only)
#
# M7 draws its up-to-500 rows from the SAME 15,000-row GUIDE_Test.csv cache
# M1-M6's heldout mode scores (Protocol A/PREFERRED, 0% incident overlap --
# see EVAL_PROTOCOL.md), filtered to evidence_field_count >= 2
# (should_use_fallback() False -- the same routing rule that decides
# LLM-eligibility everywhere else in this project). That choice, not the
# existing 999-alert train-sampled cache llm_subset_eval_improved_full209.json
# was measured against, is deliberate: the 999 cache is 55.76%
# incident-level contaminated (M2.1 PART B), and this suite's whole point is
# that every headline number here cites which protocol produced it. Using
# the contaminated pool for the one arm this script adds would undercut
# that. The existing 209-alert result is cited as corroborating context, not
# reused as this arm's number.
#
# Groq's openai/gpt-oss-20b quota is ~200,000 tokens/day, roughly 300-320
# calls/day at this pipeline's per-call cost (control_node_ablation.py). 500
# single-call classifications will not fit in one invocation of this script;
# --daily-call-budget caps how many live calls THIS invocation makes, and
# progress checkpoints to M7_CHECKPOINT_PATH (JSON Lines, one flushed write
# per row) so a second invocation on a later day resumes rather than
# re-spending quota on rows already scored.


def run_m7(daily_call_budget: int, heldout_correct_by_model: dict[str, list[bool]] | None) -> dict:
    from experiments.control_node_ablation import _is_quota_error
    from experiments.llm_subset_eval import IMPROVED_SYSTEM_PROMPT, build_alert_context, classify
    from src.agent.fallback_classifier import should_use_fallback

    holdout = load_holdout().reset_index().rename(columns={"index": "_row_index"})
    eligible = holdout[holdout.apply(lambda r: not should_use_fallback(r.to_dict()), axis=1)]
    eligible = eligible.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    target = eligible.head(M7_TARGET_N)
    print(
        f"M7: {len(target)}/{M7_TARGET_N} target LLM-eligible alerts found in the "
        f"15,000-row held-out pool ({len(eligible)} eligible in total)",
        flush=True,
    )

    scored_by_index: dict[int, dict] = {}
    if M7_CHECKPOINT_PATH.exists():
        for line in M7_CHECKPOINT_PATH.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                scored_by_index[row["_row_index"]] = row
        print(f"  resuming: {len(scored_by_index)} rows already scored from a prior invocation", flush=True)

    calls_made = 0
    quota_exhausted = False
    M7_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with M7_CHECKPOINT_PATH.open("a") as ckpt:
        for _, row in target.iterrows():
            row_index = int(row["_row_index"])
            if row_index in scored_by_index:
                continue
            if calls_made >= daily_call_budget:
                print(f"  reached this invocation's call budget ({daily_call_budget}); stopping", flush=True)
                break
            alert = row.to_dict()
            ground_truth = alert.pop("IncidentGrade")
            alert.pop("_row_index")
            context = build_alert_context(alert)
            result = classify(context, IMPROVED_SYSTEM_PROMPT)
            calls_made += 1
            record = {"_row_index": row_index, "ground_truth": ground_truth, **result}
            ckpt.write(json.dumps(record) + "\n")
            ckpt.flush()
            scored_by_index[row_index] = record
            if result.get("error") and _is_quota_error(result["error"]):
                quota_exhausted = True
                print("  quota exhausted; stopping, progress preserved in the checkpoint", flush=True)
                break
            if calls_made % 10 == 0:
                print(
                    f"  {calls_made} calls this invocation, {len(scored_by_index)}/{len(target)} total scored",
                    flush=True,
                )
            time.sleep(0.3)

    scored_rows = [scored_by_index[int(r["_row_index"])] for _, r in target.iterrows() if int(r["_row_index"]) in scored_by_index]
    y_true = [r["ground_truth"] for r in scored_rows if r.get("predicted_label")]
    y_pred = [r["predicted_label"] for r in scored_rows if r.get("predicted_label")]
    n_target = len(target)
    n_scored = len(scored_rows)
    n_labelled = len(y_true)

    result: dict = {
        "n_target": n_target,
        "n_scored_this_and_prior_invocations": n_scored,
        "n_with_a_usable_verdict": n_labelled,
        "complete": n_scored >= n_target,
        "quota_exhausted_this_invocation": quota_exhausted,
        "calls_made_this_invocation": calls_made,
        "accuracy": accuracy(y_true, y_pred) if y_true else None,
        "macro_f1": macro_f1(y_true, y_pred) if y_true else None,
        "per_class_recall": (
            {
                label: float(recall_score(y_true, y_pred, labels=[label], average="macro", zero_division=0))
                for label in TARGET_CLASSES
            }
            if y_true
            else None
        ),
        "reference_209_alert_result": (
            "experiments/results/llm_subset_eval_improved_full209.json reported 0.2823 accuracy on a "
            "55.76%-incident-overlap train-sampled pool -- corroborating context, not this arm's number "
            "(that pool is Protocol C/LAB_INFLATED; this arm is Protocol A/PREFERRED)."
        ),
    }

    if not result["complete"]:
        result["status"] = (
            f"PARTIAL: {n_scored}/{n_target} scored as of this invocation. Re-run with "
            f"--model_id M7 --mode heldout --daily-call-budget N to continue; already-scored "
            f"rows are skipped via {M7_CHECKPOINT_PATH}."
        )

    correct_m7 = {int(r["_row_index"]): (r["ground_truth"] == r.get("predicted_label")) for r in scored_rows}
    mcnemar_vs = {}
    if heldout_correct_by_model:
        for other_id in ("M6", "M3a"):
            if other_id not in heldout_correct_by_model:
                continue
            other_correct_full = heldout_correct_by_model[other_id]
            paired_m7, paired_other = [], []
            for idx, m7_correct in correct_m7.items():
                if idx < len(other_correct_full):
                    paired_m7.append(m7_correct)
                    paired_other.append(bool(other_correct_full[idx]))
            if paired_m7:
                raw = mcnemar(paired_other, paired_m7)
                other_wrong_m7_right = raw["llm_correct_rf_wrong"]
                other_right_m7_wrong = raw["rf_correct_llm_wrong"]
                odds_ratio = (
                    other_right_m7_wrong / other_wrong_m7_right
                    if other_wrong_m7_right
                    else float("inf")
                )
                mcnemar_vs[f"{other_id}_vs_M7"] = {
                    "a": other_id,
                    "b": "M7",
                    "n_paired": len(paired_m7),
                    "both_correct": raw["both_correct"],
                    f"{other_id}_correct_M7_wrong": raw["rf_correct_llm_wrong"],
                    f"M7_correct_{other_id}_wrong": raw["llm_correct_rf_wrong"],
                    "both_wrong": raw["both_wrong"],
                    "discordant_pairs": raw["discordant_pairs"],
                    "p_value": raw["p_value"],
                    "odds_ratio_a_over_b": round(odds_ratio, 4) if odds_ratio != float("inf") else None,
                }
    else:
        mcnemar_vs = {
            "status": "not computed this invocation -- run with M1-M6 in the same call "
            "(--model_id all --include-m7) to get a paired McNemar against M6/M3a"
        }
    result["mcnemar_vs_tabular"] = mcnemar_vs

    payload = {
        "experiment": "M2.4 M7: LLM-only classification on up to 500 LLM-eligible held-out alerts",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "protocol": "PREFERRED",
        "model": "Llama family via Groq (openai/gpt-oss-20b), improved prompt (Week 14)",
        **result,
    }
    OUTPUT_M7_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_M7_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nM7: acc={result['accuracy']} f1={result['macro_f1']} n_scored={n_scored}/{n_target}", flush=True)
    print(f"saved to {OUTPUT_M7_PATH}", flush=True)

    # Merge into the heldout JSON too, if it exists, so "models" in that file
    # stays the single place every arm's headline numbers live.
    if OUTPUT_HELDOUT_PATH.exists():
        heldout_payload = json.loads(OUTPUT_HELDOUT_PATH.read_text())
        heldout_payload.setdefault("models", {})["M7"] = {
            "n": n_scored,
            "accuracy": result["accuracy"],
            "macro_f1": result["macro_f1"],
            "per_class_recall": result["per_class_recall"],
            "complete": result["complete"],
        }
        heldout_payload.setdefault("mcnemar_pairs", {}).update(mcnemar_vs if heldout_correct_by_model else {})
        heldout_payload["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        OUTPUT_HELDOUT_PATH.write_text(json.dumps(heldout_payload, indent=2))
        print(f"merged M7 into {OUTPUT_HELDOUT_PATH}", flush=True)

    return result


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="M2.4: 7-classifier baseline suite (validate + heldout modes)."
    )
    parser.add_argument(
        "--model_id",
        choices=ALL_MODEL_IDS + ["all"],
        default="all",
        help="Which model(s) to run. 'all' runs M1-M6 (tabular only -- M7 is opt-in, see --include-m7).",
    )
    parser.add_argument(
        "--mode",
        choices=["validate", "heldout", "both"],
        default="both",
    )
    parser.add_argument(
        "--include-m7",
        action="store_true",
        help="Also run the LLM-only arm. Off by default: M7 spends a finite Groq daily quota "
        "(~300-320 calls/day) even on a run that only meant to re-check M1-M6.",
    )
    parser.add_argument(
        "--daily-call-budget",
        type=int,
        default=300,
        help="Max live Groq calls for M7 in this invocation (see run_m7()).",
    )
    args = parser.parse_args()

    if args.model_id == "all":
        model_ids = list(TABULAR_MODEL_IDS)
        if args.include_m7:
            model_ids.append("M7")
    elif args.model_id == "M7":
        model_ids = ["M7"]
    else:
        model_ids = [args.model_id]

    tabular_ids = [m for m in model_ids if m != "M7"]
    run_m7_flag = "M7" in model_ids

    if not TRAIN_DATA_PATH.exists() and tabular_ids:
        raise SystemExit(f"{TRAIN_DATA_PATH} not found; the tabular suite needs the real training data.")

    validate_out, heldout_out, correct_by_model = None, None, None

    if args.mode in ("validate", "both") and tabular_ids:
        print("\n" + "=" * 72)
        print("MODE: validate (5-seed GroupShuffleSplit)")
        print("=" * 72)
        validate_out = run_validate(tabular_ids)
        payload = {
            "experiment": "M2.4 5-seed GroupShuffleSplit validation across the classifier suite",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha(),
            "protocol": "ACCEPTABLE",  # GroupShuffleSplit, per EVAL_PROTOCOL.md Protocol B
            **validate_out,
        }
        OUTPUT_VALIDATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_VALIDATE_PATH.write_text(json.dumps(payload, indent=2))
        print(f"\nsaved to {OUTPUT_VALIDATE_PATH}")

    if args.mode in ("heldout", "both") and tabular_ids:
        print("\n" + "=" * 72)
        print("MODE: heldout (GUIDE_Test.csv, n=15,000)")
        print("=" * 72)
        heldout_out = run_heldout(tabular_ids)
        correct_by_model = heldout_out["_correct_by_model"]

        selection = select_best(heldout_out["models"], correct_by_model)
        mcnemar_p = (selection.get("mcnemar_best_vs_second") or {}).get("p_value")
        significant = mcnemar_p is not None and mcnemar_p < 0.05
        if selection.get("gap_exceeds_1_5_points") and significant:
            selection["selected"] = selection["best_candidate"]
            selection["selection_reason"] = "beats second-best by >1.5 pts and McNemar p<0.05"
        else:
            selection["selected"] = "M3a"
            selection["selection_reason"] = (
                "did not clear both the >1.5-point gap and McNemar p<0.05 bar -- "
                "falling back to RF (M3a), the most interpretable option"
            )

        heldout_out.pop("_correct_by_model")
        payload = {
            "experiment": "M2.4 held-out GUIDE_Test.csv (n=15,000) scoring across the classifier suite",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha(),
            "protocol": "PREFERRED",  # GUIDE_Test.csv held-out, per EVAL_PROTOCOL.md Protocol A
            **heldout_out,
        }
        OUTPUT_HELDOUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_HELDOUT_PATH.write_text(json.dumps(payload, indent=2))
        print(f"\nsaved to {OUTPUT_HELDOUT_PATH}")

        selection_payload = {
            "experiment": "M2.4 auto-selection: best classifier vs RF fallback",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha(),
            **selection,
        }
        OUTPUT_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_SELECTION_PATH.write_text(json.dumps(selection_payload, indent=2))
        print(f"saved to {OUTPUT_SELECTION_PATH}")
        print(f"\nSELECTED: {selection['selected']} ({selection['selection_reason']})")

        if selection["selected"] == "M3a" and GROUPED_CLASSIFIER_ARTIFACT.exists():
            BEST_CLASSIFIER_LINK.parent.mkdir(parents=True, exist_ok=True)
            if BEST_CLASSIFIER_LINK.is_symlink() or BEST_CLASSIFIER_LINK.exists():
                BEST_CLASSIFIER_LINK.unlink()
            BEST_CLASSIFIER_LINK.symlink_to(GROUPED_CLASSIFIER_ARTIFACT.name)
            print(f"linked {BEST_CLASSIFIER_LINK} -> {GROUPED_CLASSIFIER_ARTIFACT.name}")
        elif selection["selected"] == "M3a":
            print(
                f"selection is M3a but {GROUPED_CLASSIFIER_ARTIFACT} is not present "
                "on disk yet -- run m2_3_deploy_grouped_model.py first, then rerun "
                "this script's heldout mode to create the models/best_classifier.joblib link"
            )

    if run_m7_flag:
        print("\n" + "=" * 72)
        print("MODE: M7 (LLM-only, quota-budgeted)")
        print("=" * 72)
        run_m7(args.daily_call_budget, heldout_correct_by_model=correct_by_model)


if __name__ == "__main__":
    main()
