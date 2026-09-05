# experiments/guide_test_holdout_eval.py
#
# Every accuracy figure this project has reported so far -- the RF baseline,
# the 209-alert control experiment, the 999-alert rf_primary run -- is
# computed on a sample of datasets/GUIDE_train.csv, the file the RF is
# trained on. `grep -rn "GUIDE_Test" .` outside datasets/ returns nothing:
# datasets/GUIDE_Test.csv, the dataset's own held-out split (4.15M rows,
# same schema as GUIDE_train.csv plus one extra "Usage" column), has never
# been read by any code in this repository. rf_vs_llm_control.py already
# measures and discloses a small (1.91%, 4/209) exact-row overlap between
# the RF's training rows and its evaluation samples, judged immaterial --
# but "immaterial overlap" is not the same claim as "evaluated on data the
# model never saw," and this script is what actually closes that gap.
#
# This script scores the already-trained baseline_model.joblib against a
# freshly-drawn, class-balanced sample of GUIDE_Test.csv -- rows the RF has
# structurally never seen, not merely rows measured to mostly not overlap --
# and reports how its accuracy compares to the GUIDE_train-sampled numbers
# already committed.
#
# Fully offline (predict_proba only) except an optional 60-alert live smoke
# subset that runs the actual rf_primary graph (Groq explanation calls) to
# confirm the pipeline doesn't crash on genuinely unseen alerts and that
# explanation still cannot alter the verdict, this time on held-out data.
#
# usage (from repo root):
#   venv/bin/python experiments/guide_test_holdout_eval.py
#   venv/bin/python experiments/guide_test_holdout_eval.py --skip-live-smoke

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
from sklearn.metrics import accuracy_score, classification_report, f1_score

from src.agent.fallback_classifier import _load_model, _to_feature_frame
from src.agent.graph import build_triage_graph
from src.data.schema import TARGET_COLUMN, TARGET_CLASSES
from src.models.decision import resolve_label
from experiments.roc_auc_analysis import compute_ovr_roc_auc
from experiments.stats_utils import (
    bootstrap_auc_ci,
    bootstrap_metric_ci,
    bootstrap_two_sample_diff_ci,
)

TEST_DATA_PATH = Path("datasets/GUIDE_Test.csv")
CACHE_DIR = Path("experiments/results/evaluation_samples")
OUTPUT_PATH = Path("experiments/results/guide_test_holdout_eval.json")
RF_CONTROL_PATH = Path("experiments/results/rf_vs_llm_control.json")
RF_PRIMARY_999_PATH = Path("experiments/results/agent_metrics_week15_rf_primary.json")

SAMPLE_SEED = 42
# GUIDE_Test.csv has every GUIDE_train.csv column plus this one, which marks
# which Kaggle competition phase (public/private leaderboard) a row belongs
# to. It's not a model feature and isn't in the trained model's
# feature_names_in_, so it's dropped before scoring.
EXTRA_TEST_COLUMN = "Usage"


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _data_signature(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "size_bytes": stat.st_size, "modified_ns": stat.st_mtime_ns}


def load_balanced_test_sample(sample_size: int = 999, seed: int = SAMPLE_SEED) -> pd.DataFrame:
    """Class-balanced reservoir sample of datasets/GUIDE_Test.csv, cached.

    Mirrors load_balanced_evaluation_sample() in src/agent/evaluate.py
    (same reservoir-sampling method, same seed convention) but points at the
    held-out split instead, and is kept as a separate function rather than a
    parameter on the original -- that one is used elsewhere and changing its
    behaviour is out of scope here.
    """
    sample_per_class = sample_size // 3
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"guide_test_balanced_{sample_per_class}_per_class_seed_{seed}.csv"
    metadata_path = cache_path.with_suffix(".json")
    expected_metadata = {
        "data": _data_signature(TEST_DATA_PATH),
        "sample_per_class": sample_per_class,
        "seed": seed,
    }

    if cache_path.exists() and metadata_path.exists():
        with open(metadata_path) as file:
            if json.load(file) == expected_metadata:
                cached = pd.read_csv(cache_path)
                if len(cached) == sample_per_class * len(TARGET_CLASSES):
                    print(f"Reusing cached test-holdout sample: {cache_path}")
                    return cached

    print(f"Creating a balanced test-holdout sample by streaming {TEST_DATA_PATH}...")
    rng = np.random.default_rng(seed)
    reservoirs = {label: pd.DataFrame() for label in TARGET_CLASSES}
    rows_seen = 0
    for chunk_number, chunk in enumerate(
        pd.read_csv(TEST_DATA_PATH, chunksize=100_000, low_memory=False), start=1
    ):
        chunk = chunk.dropna(subset=[TARGET_COLUMN])
        rows_seen += len(chunk)
        for label in TARGET_CLASSES:
            candidates = chunk[chunk[TARGET_COLUMN] == label].copy()
            if candidates.empty:
                continue
            candidates["_sample_key"] = rng.random(len(candidates))
            reservoirs[label] = pd.concat([reservoirs[label], candidates], ignore_index=True).nsmallest(
                sample_per_class, "_sample_key"
            )
        if chunk_number % 10 == 0:
            print(f"  scanned {rows_seen:,} rows...", flush=True)

    missing = [label for label, sample in reservoirs.items() if len(sample) < sample_per_class]
    if missing:
        raise ValueError(f"Not enough test-split examples for classes: {', '.join(missing)}")

    sample = pd.concat(reservoirs.values(), ignore_index=True).drop(columns="_sample_key")
    if EXTRA_TEST_COLUMN in sample.columns:
        sample = sample.drop(columns=[EXTRA_TEST_COLUMN])
    sample.to_csv(cache_path, index=False)
    with open(metadata_path, "w") as file:
        json.dump(expected_metadata, file, indent=2)
    print(f"Cached test-holdout sample: {cache_path}")
    return sample


def score_holdout(sample: pd.DataFrame) -> dict:
    """Score every row with the trained RF, capturing full predict_proba vectors."""
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]
    classes = [str(c) for c in model.classes_]
    model_features = set(model.feature_names_in_)

    y_true, y_pred, proba_rows, per_alert = [], [], [], []
    unknown_category_alerts = 0
    unknown_category_field_total = 0
    categorical_field_total = 0

    for row_index, row in sample.iterrows():
        alert = row.to_dict()
        ground_truth = alert.pop(TARGET_COLUMN)
        features = _to_feature_frame(alert, model, encoders)

        encoded_categorical_cols = [c for c in encoders if c in model_features]
        row_unknown = 0
        for col in encoded_categorical_cols:
            categorical_field_total += 1
            if int(features.iloc[0][col]) == -1:
                row_unknown += 1
        if row_unknown:
            unknown_category_alerts += 1
        unknown_category_field_total += row_unknown

        proba = model.predict_proba(features)[0]
        order = np.argsort(proba)[::-1]
        label = resolve_label(model.classes_, proba)

        y_true.append(ground_truth)
        y_pred.append(label)
        proba_rows.append(proba)
        per_alert.append(
            {
                "_row_index": int(row_index),
                "ground_truth": ground_truth,
                "rf_predicted": label,
                "rf_top1_probability": round(float(proba[order[0]]), 4),
                "unknown_category_fields": row_unknown,
            }
        )

    proba_matrix = np.array(proba_rows)
    roc = compute_ovr_roc_auc(y_true, proba_matrix, classes=classes)
    roc["macro_auc_bootstrap_ci"] = bootstrap_auc_ci(y_true, proba_matrix, classes=classes)

    return {
        "n": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "accuracy_bootstrap_ci": bootstrap_metric_ci(
            y_true, y_pred, lambda t, p: accuracy_score(t, p)
        ),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
        "macro_f1_bootstrap_ci": bootstrap_metric_ci(
            y_true, y_pred, lambda t, p: f1_score(t, p, average="macro", zero_division=0)
        ),
        "classification_report": classification_report(y_true, y_pred, zero_division=0, digits=3),
        "roc_auc": roc,
        "unknown_category_diagnostic": {
            "unknown_category_alert_rate": round(unknown_category_alerts / len(y_true), 4) if y_true else None,
            "unknown_category_field_rate": (
                round(unknown_category_field_total / categorical_field_total, 4)
                if categorical_field_total
                else None
            ),
            "explanation": (
                "transform_with_encoders() (src/data/preprocess.py) maps any "
                "categorical value the training encoders never saw to -1 instead "
                "of crashing. On a genuinely held-out split this can fire for "
                "the first time; both rates report how often it does."
            ),
        },
        "per_alert_results": per_alert,
    }


def train_vs_test_comparison(test_scores: dict) -> dict:
    """Lay the new test-holdout numbers next to the two existing GUIDE_train-sourced runs."""
    comparison = {
        "test_holdout_999": {"accuracy": test_scores["accuracy"], "macro_f1": test_scores["macro_f1"], "n": test_scores["n"]},
    }
    if RF_CONTROL_PATH.exists():
        control = json.loads(RF_CONTROL_PATH.read_text())
        rf = control.get("randomforest", {})
        comparison["train_sampled_209_evidence_rich"] = {
            "accuracy": rf.get("accuracy"), "macro_f1": rf.get("macro_f1"), "n": rf.get("n"),
        }
    if RF_PRIMARY_999_PATH.exists():
        primary = json.loads(RF_PRIMARY_999_PATH.read_text())
        comparison["train_sampled_999_rf_primary_pipeline"] = {
            "accuracy": primary.get("accuracy"), "macro_f1": primary.get("macro_f1"), "n": primary.get("sample_size"),
        }
    return comparison


def compute_gap_significance(test_scores: dict) -> dict | None:
    """Bootstrap CI on (held-out accuracy) - (train-sampled accuracy).

    test_holdout_999 and train_sampled_999_rf_primary_pipeline are two
    INDEPENDENT samples of different alerts scored by the same static model
    -- not the same rows scored two ways -- so this is a two-sample
    bootstrap on the difference, not a McNemar paired test. Replaces the
    earlier fixed "+/-3pt noise band" heuristic with an actual computed
    interval on the gap.
    """
    if not RF_PRIMARY_999_PATH.exists():
        return None
    primary = json.loads(RF_PRIMARY_999_PATH.read_text())
    train_rows = primary.get("per_alert_results")
    if not train_rows:
        return None

    y_true_test = [r["ground_truth"] for r in test_scores["per_alert_results"]]
    y_pred_test = [r["rf_predicted"] for r in test_scores["per_alert_results"]]
    y_true_train = [r["ground_truth"] for r in train_rows]
    y_pred_train = [r["predicted"] for r in train_rows]

    return bootstrap_two_sample_diff_ci(
        y_true_test, y_pred_test, y_true_train, y_pred_train,
        metric_fn=lambda t, p: accuracy_score(t, p),
    )


def compute_interpretation(comparison: dict, gap_significance: dict | None) -> str:
    """State, from the actual numbers, whether test-holdout accuracy held up."""
    test_acc = comparison["test_holdout_999"]["accuracy"]
    reference = comparison.get("train_sampled_999_rf_primary_pipeline") or comparison.get(
        "train_sampled_209_evidence_rich"
    )
    if not reference or reference.get("accuracy") is None:
        return "No comparable GUIDE_train-sampled run was found to compare against."

    train_acc = reference["accuracy"]
    gap = round(test_acc - train_acc, 4)
    verdict = "held up" if abs(gap) < 1e-9 else ("improved" if gap > 0 else "dropped")

    base = (
        f"Accuracy on the held-out GUIDE_Test.csv sample ({test_acc}) {verdict} "
        f"relative to the GUIDE_train-sampled run ({train_acc}), a gap of {gap:+.4f}."
    )
    if gap_significance is None:
        return base + " (No per-alert train-sampled results were available to test this gap for significance.)"
    return base + " " + gap_significance["interpretation"]


def run_live_smoke(sample: pd.DataFrame, n: int = 60) -> dict:
    """Run the real rf_primary graph (live LLM explanation calls) on unseen rows.

    Confirms two things at once, specifically on held-out data: the pipeline
    doesn't crash on rows the RF has never seen, and predicted_label/
    confidence from the live graph exactly match the offline predict_proba
    result for the same rows -- explanation cannot change the verdict.
    """
    per_class = n // 3
    subset = pd.concat(
        [sample[sample[TARGET_COLUMN] == cls].head(per_class) for cls in TARGET_CLASSES],
        ignore_index=True,
    )
    graph = build_triage_graph(mode="rf_primary")
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    mismatches, errors, rationale_statuses = [], [], {}
    for _, row in subset.iterrows():
        alert = row.to_dict()
        alert.pop(TARGET_COLUMN, None)
        offline_features = _to_feature_frame(alert, model, encoders)
        offline_proba = model.predict_proba(offline_features)[0]
        # Must use the same tie-break as the graph does, or an exactly-tied
        # alert reads as a wiring mismatch when both paths are behaving
        # correctly. np.argmax resolves a tie toward BenignPositive while the
        # deployed path resolves it toward TruePositive.
        offline_label = resolve_label(model.classes_, offline_proba)

        try:
            result = graph.invoke({"raw_alert": alert})
        except Exception as exc:
            errors.append(str(exc))
            continue

        status = result.get("rationale_status", "none")
        rationale_statuses[status] = rationale_statuses.get(status, 0) + 1
        if result.get("predicted_label") != offline_label:
            mismatches.append(
                {
                    "offline_label": offline_label,
                    "live_label": result.get("predicted_label"),
                }
            )

    return {
        "n": len(subset),
        "crash_count": len(errors),
        "errors": errors,
        "rationale_status_distribution": rationale_statuses,
        "verdict_mismatches": mismatches,
        "verdict_matches_offline_prediction": len(mismatches) == 0 and not errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the trained RF on the held-out GUIDE_Test.csv split.")
    parser.add_argument("--sample-size", type=int, default=999)
    parser.add_argument("--skip-live-smoke", action="store_true")
    args = parser.parse_args()

    sample = load_balanced_test_sample(args.sample_size).reset_index(drop=True)
    print(f"scoring {len(sample)} held-out alerts...")
    test_scores = score_holdout(sample)

    comparison = train_vs_test_comparison(test_scores)
    gap_significance = compute_gap_significance(test_scores)
    interpretation = compute_interpretation(comparison, gap_significance)

    output = {
        "experiment": "RandomForest evaluated on datasets/GUIDE_Test.csv (the never-touched held-out split)",
        "question": (
            "Every reported accuracy figure so far samples GUIDE_train.csv, the "
            "file the RF is trained on -- with a small, disclosed, judged-immaterial "
            "training-row overlap (rf_vs_llm_control.json). This asks whether "
            "accuracy holds on rows the RF has never had any chance to see."
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "rf_model": "RandomForestClassifier, experiments/results/baseline_model.joblib",
        "test_data_path": str(TEST_DATA_PATH),
        "test_sample_path": str(
            CACHE_DIR / f"guide_test_balanced_{args.sample_size // 3}_per_class_seed_{SAMPLE_SEED}.csv"
        ),
        "train_vs_test_comparison": comparison,
        "gap_significance": gap_significance,
        "interpretation": interpretation,
        "test_holdout": test_scores,
    }

    if not args.skip_live_smoke:
        print("running 60-alert live smoke subset (rf_primary graph, real Groq calls)...")
        output["live_smoke_subset"] = run_live_smoke(sample)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 68)
    print("GUIDE_Test.csv HOLDOUT EVALUATION")
    print("=" * 68)
    acc_ci = test_scores["accuracy_bootstrap_ci"]
    print(
        f"  accuracy: {test_scores['accuracy']} (95% CI [{acc_ci['ci_lower']}, {acc_ci['ci_upper']}])"
        f"   macro F1: {test_scores['macro_f1']}"
    )
    print(f"  macro AUC: {test_scores['roc_auc']['macro_auc']}")
    print(f"  unknown-category alert rate: {test_scores['unknown_category_diagnostic']['unknown_category_alert_rate']}")
    print(f"\n  {interpretation}")
    if "live_smoke_subset" in output:
        smoke = output["live_smoke_subset"]
        print(
            f"\n  live smoke ({smoke['n']} alerts): crashes={smoke['crash_count']}, "
            f"verdict matches offline: {smoke['verdict_matches_offline_prediction']}"
        )
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
