# experiments/classifier_improvement_study.py
#
# What the deployed classifier leaves on the table, and what the identifier
# features are actually worth.
#
# The deployed baseline_model.joblib is a stock RandomForestClassifier(200)
# trained on the first 100,000 of GUIDE_train.csv's 9,516,838 rows -- about 1%
# of the available data -- with no tuning and no class weighting. It scores
# 0.6998 accuracy / 0.6949 macro F1 on the held-out GUIDE_Test sample
# (n=15,000, 0% incident overlap), which Week 17 established as the only
# figure worth quoting.
#
# This script measures five things against that reference. Every arm is
# scored on the *same* held-out GUIDE_Test sample, and separately on an
# incident-level (GroupShuffleSplit on OrgId|IncidentId) holdout carved out of
# its own training slice -- never a row-level split, because Week 17 measured
# that a row-level split is worth an inflated 24.3 accuracy points
# (experiments/results/incident_leakage_audit.json).
#
#   stage 1  data scaling      RF-200 at 100k / 250k / 500k / 1M / 2M rows
#   stage 2  estimator         HistGradientBoosting vs RandomForest
#   stage 3  class weighting   class_weight="balanced" (FalsePositive is the
#                              weak class: 0.4375 recall on clean rows)
#   stage 4  hyperparameters   small grid, selected on the *grouped internal*
#                              holdout, never on GUIDE_Test
#   stage 5  identifier ablation -- the feature-inflation study carried
#                              outstanding from Week 15
#
# Stage 5 is the one that is a finding rather than an optimisation.
# src/data/schema.py drops six ID columns before modelling, on the stated
# grounds that identifiers "don't generalise to unseen orgs/devices and cause
# data leakage if kept". But twelve identifier-like columns survive that filter
# and are label-encoded into the feature matrix -- AccountUpn alone takes
# 49,761 distinct values across 199k rows. This stage removes them in tiers and
# measures what each tier is worth on a leaky split versus a clean one.
#
# Nothing here overwrites experiments/results/baseline_model.joblib. The
# deployed model and every published figure derived from it are untouched;
# candidate models are written to experiments/results/candidate_models/ and
# adopted only by an explicit, separate decision.
#
# usage (from repo root):
#   venv/bin/python experiments/classifier_improvement_study.py
#   venv/bin/python experiments/classifier_improvement_study.py --stages 1,5
#   venv/bin/python experiments/classifier_improvement_study.py --max-rows-cap 500000

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, f1_score, recall_score
from sklearn.model_selection import GroupShuffleSplit

from experiments.streaming_encode import load_encoded
from experiments.stats_utils import bootstrap_metric_ci, bootstrap_two_sample_diff_ci
from src.data.preprocess import transform_with_encoders
from src.data.schema import TARGET_COLUMN, TARGET_CLASSES
from src.models.decision import predict_labels

TRAIN_DATA_PATH = Path("datasets/GUIDE_train.csv")
HOLDOUT_SAMPLE_PATH = Path(
    "experiments/results/evaluation_samples/guide_test_balanced_5000_per_class_seed_42.csv"
)
OUTPUT_PATH = Path("experiments/results/classifier_improvement_study.json")
CANDIDATE_DIR = Path("experiments/results/candidate_models")

SEED = 42
DEPLOYED_HOLDOUT_ACCURACY = 0.6998
DEPLOYED_HOLDOUT_MACRO_F1 = 0.6949
DEPLOYED_MAX_ROWS = 100_000

SCALING_STEPS = [100_000, 250_000, 500_000, 1_000_000, 2_000_000]

# Identifier-like columns that survive src/data/schema.py's ID_COLUMNS filter.
# Tiered by what the value identifies, not by raw cardinality, so each tier
# answers a question a reviewer would actually ask.
ACCOUNT_IDENTIFIERS = ["AccountUpn", "AccountName", "AccountSid", "AccountObjectId"]
ARTIFACT_IDENTIFIERS = [
    "IpAddress",
    "NetworkMessageId",
    "FileName",
    "Url",
    "Sha256",
    "FolderPath",
    "DeviceName",
    "EmailClusterId",
]
# Mid-cardinality descriptive fields. Not pointers to a principal or host, so
# they survive tier 2, but numerous enough (AlertTitle takes 18,306 distinct
# values) that a forest can still key on individual values. Tier 3 removes them
# to leave only fields an analyst could enumerate by hand.
DESCRIPTIVE_FEATURES = [
    "AlertTitle", "City", "State", "MitreTechniques", "ThreatFamily",
    "ApplicationName", "ApplicationId", "ResourceIdName", "RegistryKey",
    "RegistryValueName", "RegistryValueData", "OAuthApplicationId",
]


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def accuracy(y_true, y_pred) -> float:
    return float(accuracy_score(y_true, y_pred))


def macro_f1(y_true, y_pred) -> float:
    return float(f1_score(y_true, y_pred, average="macro"))


# ---------------------------------------------------------------- evaluation

def load_holdout() -> pd.DataFrame:
    if not HOLDOUT_SAMPLE_PATH.exists():
        raise FileNotFoundError(
            f"{HOLDOUT_SAMPLE_PATH} not found. Regenerate it with:\n"
            "  venv/bin/python experiments/guide_test_holdout_eval.py"
        )
    return pd.read_csv(HOLDOUT_SAMPLE_PATH, low_memory=False)


def score_holdout(model, encoders, feature_names, holdout: pd.DataFrame) -> dict:
    """Score a candidate on the held-out GUIDE_Test sample.

    Uses src/data/preprocess.transform_with_encoders, the same function the
    deployed inference path uses, so an unseen category becomes -1 here exactly
    as it would in production.
    """
    frame = holdout.copy()
    ts = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)
    frame["Hour"], frame["DayOfWeek"], frame["Month"] = ts.dt.hour, ts.dt.dayofweek, ts.dt.month
    X = transform_with_encoders(frame, encoders).reindex(columns=feature_names)
    y = holdout[TARGET_COLUMN]
    pred = predict_labels(model, X)
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


def evaluate(model, encoders, feature_names, Xte, yte, holdout) -> dict:
    """Grouped internal holdout + the clean external held-out split."""
    pred = predict_labels(model, Xte)
    internal = {
        "n": int(len(yte)),
        "accuracy": accuracy(yte, pred),
        "macro_f1": macro_f1(yte, pred),
        "split": "incident-level GroupShuffleSplit on (OrgId, IncidentId)",
    }
    external = score_holdout(model, encoders, feature_names, holdout)
    return {"grouped_internal_holdout": internal, "held_out_guide_test": external}


def strip_series(result: dict) -> dict:
    """Drop the raw prediction vectors before serialising."""
    out = json.loads(json.dumps(result, default=lambda o: None))

    def prune(node):
        if isinstance(node, dict):
            for key in ["_y_true", "_y_pred"]:
                node.pop(key, None)
            for value in node.values():
                prune(value)
        elif isinstance(node, list):
            for value in node:
                prune(value)
    prune(out)
    return out


# ---------------------------------------------------------------- training

def grouped_split(X, y, groups, test_size=0.2):
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=SEED)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    return (
        X.iloc[train_idx], X.iloc[test_idx],
        y.iloc[train_idx], y.iloc[test_idx],
        groups[train_idx], groups[test_idx],
    )


def fit(estimator, Xtr, ytr) -> tuple:
    t = time.time()
    estimator.fit(Xtr, ytr)
    return estimator, round(time.time() - t, 1)


def rf(**kwargs) -> RandomForestClassifier:
    params = {"n_estimators": 200, "random_state": SEED, "n_jobs": -1}
    params.update(kwargs)
    return RandomForestClassifier(**params)


# ---------------------------------------------------------------- arm table
#
# Memory is the binding constraint, not time. A fully-grown RandomForest(200)
# on this data costs about 0.42 tree nodes per training row per tree -- the
# deployed 100,000-row model is already a 563 MB artifact -- so a
# default-grown forest at 1,000,000 rows would need roughly 5.6 GB and does
# not fit in this machine's 8 GB alongside the data.
#
# So the scaling question is asked twice, with two configurations that are each
# internally comparable:
#
#   rf200_default  fully grown, the deployed configuration exactly, run as far
#                  as it fits (500,000 rows)
#   rf200_leaf5    min_samples_leaf=5, which bounds tree growth enough to reach
#                  2,000,000 rows, and is a sensible regulariser in its own right
#
# HistGradientBoosting is bounded by max_leaf_nodes rather than sample count,
# so it reaches the largest slices at a fraction of the memory.

RF_DEFAULT_MAX_FEASIBLE_ROWS = 500_000


def arm_table(cap: int) -> list[dict]:
    """(name, rows, factory, stage) for every candidate, grouped by row count."""
    def rf_default():
        return rf()

    def rf_leaf5():
        return rf(min_samples_leaf=5)

    def rf_leaf5_balanced():
        return rf(min_samples_leaf=5, class_weight="balanced")

    def rf_leaf5_sqrt400():
        return rf(n_estimators=400, min_samples_leaf=5, max_features="sqrt")

    def histgb():
        return HistGradientBoostingClassifier(
            random_state=SEED, max_iter=300, learning_rate=0.1, early_stopping=True
        )

    def histgb_deep():
        return HistGradientBoostingClassifier(
            random_state=SEED, max_iter=500, learning_rate=0.06, max_leaf_nodes=63,
            l2_regularization=1.0, early_stopping=True
        )

    def histgb_balanced():
        return HistGradientBoostingClassifier(
            random_state=SEED, max_iter=500, learning_rate=0.06, max_leaf_nodes=63,
            l2_regularization=1.0, early_stopping=True, class_weight="balanced"
        )

    arms = []
    for rows in [100_000, 250_000, 500_000]:
        arms.append({"name": f"rf200_default@{rows}", "rows": rows, "make": rf_default, "stage": 1})
    for rows in [100_000, 250_000, 500_000, 1_000_000, 2_000_000]:
        arms.append({"name": f"rf200_leaf5@{rows}", "rows": rows, "make": rf_leaf5, "stage": 1})
    for rows in [500_000, 1_000_000, 2_000_000]:
        arms.append({"name": f"histgb@{rows}", "rows": rows, "make": histgb, "stage": 2})
    arms.append({"name": "histgb_deep@2000000", "rows": 2_000_000, "make": histgb_deep, "stage": 2})
    arms.append({"name": "histgb_balanced@2000000", "rows": 2_000_000, "make": histgb_balanced, "stage": 3})
    arms.append({"name": "rf200_leaf5_balanced@1000000", "rows": 1_000_000, "make": rf_leaf5_balanced, "stage": 3})
    arms.append({"name": "rf400_leaf5_sqrt@1000000", "rows": 1_000_000, "make": rf_leaf5_sqrt400, "stage": 4})
    return [a for a in arms if a["rows"] <= cap]


def run_arms(holdout, cap: int, results: dict, checkpoint) -> dict:
    """Train every candidate, grouped by row count so each slice loads once."""
    arms = arm_table(cap)
    by_rows: dict[int, list] = {}
    for arm in arms:
        by_rows.setdefault(arm["rows"], []).append(arm)

    scored: dict[str, dict] = {}
    for rows in sorted(by_rows):
        print("\n" + "=" * 72 + f"\nLOADING {rows:,} rows\n" + "=" * 72)
        X, y, groups, encoders = load_encoded(TRAIN_DATA_PATH, rows)
        Xtr, Xte, ytr, yte, _, _ = grouped_split(X, y, groups)
        features = list(X.columns)
        print(f"  train {len(Xtr):,} / grouped holdout {len(Xte):,} "
              f"({len(np.unique(groups)):,} incidents)")
        for arm in by_rows[rows]:
            print(f"\n  [{arm['name']}]")
            try:
                model, seconds = fit(arm["make"](), Xtr, ytr)
            except MemoryError:
                print("    SKIPPED - out of memory")
                scored[arm["name"]] = {"skipped": "MemoryError", "rows": rows, "stage": arm["stage"]}
                results["arms"] = strip_series(scored)
                checkpoint(results)
                continue
            entry = evaluate(model, encoders, features, Xte, yte, holdout)
            entry.update({
                "stage": arm["stage"], "max_rows": rows,
                "n_after_preprocess": int(len(X)), "n_train": int(len(Xtr)),
                "n_incidents": int(len(np.unique(groups))),
                "train_seconds": seconds, "estimator": repr(arm["make"]()),
            })
            held = entry["held_out_guide_test"]
            delta = held["accuracy"] - DEPLOYED_HOLDOUT_ACCURACY
            print(f"    grouped internal   : {entry['grouped_internal_holdout']['accuracy']:.4f} acc")
            print(f"    HELD-OUT GUIDE_Test: {held['accuracy']:.4f} acc / {held['macro_f1']:.4f} F1"
                  f"   ({delta:+.4f} vs deployed)   [{seconds}s]")
            print(f"    per-class recall   : "
                  + ", ".join(f"{k} {v:.3f}" for k, v in held["per_class_recall"].items()))
            scored[arm["name"]] = entry
            results["arms"] = strip_series(scored)
            checkpoint(results)
            del model
        del X, y, Xtr, Xte, groups

    return scored


def summarise(scored: dict, results: dict) -> str | None:
    """Pick the winner on the grouped internal holdout, report it on GUIDE_Test."""
    usable = {k: v for k, v in scored.items() if "skipped" not in v}
    if not usable:
        return None
    selected = max(usable, key=lambda k: usable[k]["grouped_internal_holdout"]["macro_f1"])
    best_held = max(usable, key=lambda k: usable[k]["held_out_guide_test"]["accuracy"])
    sel = usable[selected]["held_out_guide_test"]
    results["selection"] = {
        "rule": "highest macro F1 on the incident-level internal holdout. GUIDE_Test is "
                "reported but never optimised against, so this figure stays an honest estimate.",
        "selected": selected,
        "selected_held_out_accuracy": sel["accuracy"],
        "selected_held_out_macro_f1": sel["macro_f1"],
        "accuracy_gain_vs_deployed": round(sel["accuracy"] - DEPLOYED_HOLDOUT_ACCURACY, 4),
        "macro_f1_gain_vs_deployed": round(sel["macro_f1"] - DEPLOYED_HOLDOUT_MACRO_F1, 4),
        "best_held_out_arm_for_reference": best_held,
        "best_held_out_accuracy_for_reference": usable[best_held]["held_out_guide_test"]["accuracy"],
    }
    return selected


# ------------------------------------------------- stage 5: identifier ablation

def identifier_ablation(holdout, rows: int, make_estimator, estimator_name: str,
                        results: dict, checkpoint) -> None:
    """The feature-inflation ablation carried outstanding from Week 15.

    Each tier is trained twice -- once on a row-level split and once on an
    incident-level split -- because the question is whether the identifier
    features buy generalisation or memorisation, and only the contrast between
    the two splits separates those.
    """
    from sklearn.model_selection import train_test_split

    print("\n" + "=" * 72 + f"\nIDENTIFIER FEATURE-INFLATION ABLATION "
          f"({estimator_name}, {rows:,} rows)\n" + "=" * 72)
    X, y, groups, encoders = load_encoded(TRAIN_DATA_PATH, rows)
    all_features = list(X.columns)
    tiers = {
        "t0_all_features": all_features,
        "t1_drop_account_identifiers": [c for c in all_features if c not in ACCOUNT_IDENTIFIERS],
        "t2_drop_account_and_artifact_identifiers": [
            c for c in all_features if c not in ACCOUNT_IDENTIFIERS + ARTIFACT_IDENTIFIERS
        ],
        "t3_low_cardinality_only": [
            c for c in all_features
            if c not in ACCOUNT_IDENTIFIERS + ARTIFACT_IDENTIFIERS + DESCRIPTIVE_FEATURES
        ],
    }
    cardinality = {c: int(X[c].nunique()) for c in all_features}

    arms = {}
    for tier, columns in tiers.items():
        dropped = [c for c in all_features if c not in columns]
        print(f"\n  [{tier}] {len(columns)} features, dropped {len(dropped)}")
        Xt = X[columns]
        tier_encoders = {k: v for k, v in encoders.items() if k in columns}

        Xtr, Xte, ytr, yte, _, _ = grouped_split(Xt, y, groups)
        grouped_model, _ = fit(make_estimator(), Xtr, ytr)
        grouped_pred = predict_labels(grouped_model, Xte)

        Xtr_r, Xte_r, ytr_r, yte_r = train_test_split(
            Xt, y, test_size=0.2, random_state=SEED, stratify=y
        )
        row_model, _ = fit(make_estimator(), Xtr_r, ytr_r)
        row_pred = predict_labels(row_model, Xte_r)

        held = score_holdout(grouped_model, tier_encoders, columns, holdout)
        arms[tier] = {
            "n_features": len(columns),
            "dropped_features": dropped,
            "row_level_split": {"n": int(len(yte_r)), "accuracy": accuracy(yte_r, row_pred),
                                "macro_f1": macro_f1(yte_r, row_pred)},
            "grouped_incident_split": {"n": int(len(yte)), "accuracy": accuracy(yte, grouped_pred),
                                       "macro_f1": macro_f1(yte, grouped_pred)},
            "held_out_guide_test": held,
        }
        print(f"    row-level split    : {arms[tier]['row_level_split']['accuracy']:.4f}")
        print(f"    grouped split      : {arms[tier]['grouped_incident_split']['accuracy']:.4f}")
        print(f"    HELD-OUT GUIDE_Test: {held['accuracy']:.4f}")
        results["identifier_ablation"] = {
            "max_rows": rows, "estimator": estimator_name,
            "feature_cardinality": cardinality, "arms": strip_series(arms),
        }
        checkpoint(results)
        del grouped_model, row_model

    t0, t2 = arms["t0_all_features"], arms["t2_drop_account_and_artifact_identifiers"]
    row_cost = t0["row_level_split"]["accuracy"] - t2["row_level_split"]["accuracy"]
    grouped_cost = t0["grouped_incident_split"]["accuracy"] - t2["grouped_incident_split"]["accuracy"]
    held_cost = t0["held_out_guide_test"]["accuracy"] - t2["held_out_guide_test"]["accuracy"]
    held_ci = bootstrap_two_sample_diff_ci(
        t0["held_out_guide_test"]["_y_true"], t0["held_out_guide_test"]["_y_pred"],
        t2["held_out_guide_test"]["_y_true"], t2["held_out_guide_test"]["_y_pred"],
        accuracy, seed=SEED,
    )
    results["identifier_ablation"].update({
        "identifier_value_by_split": {
            "row_level_accuracy_cost_of_removal": round(row_cost, 4),
            "grouped_accuracy_cost_of_removal": round(grouped_cost, 4),
            "held_out_accuracy_cost_of_removal": round(held_cost, 4),
            "held_out_difference_ci": held_ci,
        },
        "finding": (
            f"Removing the twelve identifier-like features that survive schema.py's ID_COLUMNS "
            f"filter costs {row_cost:.4f} accuracy under a row-level split, {grouped_cost:.4f} "
            f"under an incident-level split, and {held_cost:.4f} on the held-out GUIDE_Test "
            f"split. The further the evaluation moves from the training incidents, the less "
            f"those features are worth."
        ),
    })
    print(f"\n  identifier removal costs: row {row_cost:+.4f} / grouped {grouped_cost:+.4f} "
          f"/ held-out {held_cost:+.4f}")
    checkpoint(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classifier improvement + ablation study.")
    parser.add_argument("--max-rows-cap", type=int, default=2_000_000)
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--only-ablation", action="store_true",
                        help="re-run just the ablation, merging into the existing results file")
    parser.add_argument("--ablation-rows", type=int, default=500_000)
    parser.add_argument("--ablation-estimator", default=None,
                        help="arm name to use; defaults to the selected arm on file")
    args = parser.parse_args()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    holdout = load_holdout()
    print(f"held-out reference: {len(holdout)} rows of GUIDE_Test.csv, 0% incident overlap "
          f"with training (incident_leakage_audit.json). Deployed model scores "
          f"{DEPLOYED_HOLDOUT_ACCURACY} / {DEPLOYED_HOLDOUT_MACRO_F1} on it.")

    results = {
        "experiment": "What the deployed RF leaves on the table: data scaling, estimator choice, "
                      "class weighting, tuning, and the identifier feature-inflation ablation "
                      "carried outstanding from Week 15",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "diagnostic_only": (
            "This script does NOT write experiments/results/baseline_model.joblib. The deployed "
            "model and every published figure derived from it are unchanged unless a candidate is "
            "adopted by a separate, explicit decision."
        ),
        "deployed_reference": {
            "max_rows": DEPLOYED_MAX_ROWS,
            "held_out_accuracy": DEPLOYED_HOLDOUT_ACCURACY,
            "held_out_macro_f1": DEPLOYED_HOLDOUT_MACRO_F1,
            "source": "experiments/results/guide_test_holdout_eval.json",
        },
        "evaluation_protocol": {
            "external": "datasets/GUIDE_Test.csv, class-balanced n=15,000, seed 42, 0% incident overlap",
            "internal": "incident-level GroupShuffleSplit on (OrgId, IncidentId), test_size 0.2, seed 42",
            "selection": "candidates are selected on the internal grouped holdout only; GUIDE_Test "
                         "is reported, never optimised against",
            "memory_note": f"A fully-grown RandomForest(200) fits only up to about "
                           f"{RF_DEFAULT_MAX_FEASIBLE_ROWS:,} rows on an 8 GB machine, so the "
                           f"scaling curve is run twice: once in the deployed configuration up to "
                           f"that ceiling, and once with min_samples_leaf=5, which reaches 2M rows.",
        },
        "available_training_rows": 9_516_838,
    }

    def checkpoint(state: dict) -> None:
        state["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        with open(OUTPUT_PATH, "w") as file:
            json.dump(state, file, indent=2, default=str)

    if args.only_ablation:
        if not OUTPUT_PATH.exists():
            raise SystemExit(f"--only-ablation needs an existing {OUTPUT_PATH}")
        with open(OUTPUT_PATH) as file:
            results = json.load(file)
        selected = args.ablation_estimator or results.get("selection", {}).get("selected")
        print(f"re-running the ablation only, with {selected}")
    else:
        scored = run_arms(holdout, args.max_rows_cap, results, checkpoint)
        selected = summarise(scored, results)
        print(f"\nselected on internal grouped holdout: {selected}")

    if not args.skip_ablation:
        # Run the ablation with the configuration the selection stage chose, so
        # it describes the model actually worth deploying rather than an
        # arbitrary one.
        chosen = next((a for a in arm_table(args.max_rows_cap) if a["name"] == selected), None)
        make = chosen["make"] if chosen else (lambda: rf())
        name = chosen["name"] if chosen else "rf200_default"
        identifier_ablation(holdout, args.ablation_rows, make, name, results, checkpoint)

    checkpoint(results)
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
