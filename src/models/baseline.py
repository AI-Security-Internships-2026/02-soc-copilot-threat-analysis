"""
Baseline triage classifier: predicts IncidentGrade (TruePositive /
BenignPositive / FalsePositive) from alert features using a Random Forest.

This is intentionally a classical ML baseline, not the LLM pipeline. Per
proposal.md (RQ1), the LLM-based triage agent needs a reference point to be
evaluated against -- this is that reference point. The LLM/LangGraph agent
is the next implementation milestone, built once the architecture doc
(Week 3) is finalised.

Usage:
    python -m src.models.baseline
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split

from src.data.load_data import REAL_DATA_PATH, SAMPLE_DATA_PATH, load_alerts
from src.data.preprocess import preprocess

RESULTS_PATH = Path("experiments/results/baseline_metrics.json")
MODEL_PATH = Path("experiments/results/baseline_model.joblib")
DEFAULT_MAX_ROWS = 100_000
TREE_BATCH_SIZE = 10
TOTAL_TREES = 200
ARTIFACT_FORMAT_VERSION = 1


def _active_data_path() -> Path:
    return REAL_DATA_PATH if REAL_DATA_PATH.exists() else SAMPLE_DATA_PATH


def _file_signature(path: Path) -> dict:
    """Cheap provenance check; changes to the source data invalidate reuse."""
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_metadata(max_rows: int | None, test_size: float, random_state: int) -> dict:
    """Describe every input that must match before an artifact can be reused."""
    return {
        "format_version": ARTIFACT_FORMAT_VERSION,
        "data": _file_signature(_active_data_path()),
        "preprocess_sha256": _source_hash(Path("src/data/preprocess.py")),
        "schema_sha256": _source_hash(Path("src/data/schema.py")),
        "max_rows": max_rows,
        "test_size": test_size,
        "random_state": random_state,
        "n_estimators": TOTAL_TREES,
    }


def load_reusable_artifact(metadata: dict) -> dict | None:
    """Load a compatible saved RF artifact without reading the CSV again."""
    if not MODEL_PATH.exists():
        return None
    try:
        artifact = joblib.load(MODEL_PATH)
    except Exception as exc:
        print(f"Saved baseline could not be read ({exc}); a new model will be trained.")
        return None
    if not isinstance(artifact, dict) or {"model", "encoders", "metadata"} - artifact.keys():
        print("Saved baseline is missing reusable encoders or provenance metadata; a fresh artifact is required.")
        return None
    if artifact["metadata"] != metadata:
        print("Saved baseline inputs or preprocessing changed; retraining a fresh artifact.")
        return None
    print(f"Reusing saved baseline artifact: {MODEL_PATH}")
    return artifact


def _atomically_save(artifact: dict, metrics: dict) -> None:
    """Replace results only after a complete train/evaluation succeeds."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=RESULTS_PATH.parent, delete=False) as model_file:
        model_tmp = Path(model_file.name)
    with tempfile.NamedTemporaryFile(mode="w", dir=RESULTS_PATH.parent, delete=False) as metrics_file:
        json.dump(metrics, metrics_file, indent=2)
        metrics_tmp = Path(metrics_file.name)
    try:
        joblib.dump(artifact, model_tmp)
        os.replace(model_tmp, MODEL_PATH)
        os.replace(metrics_tmp, RESULTS_PATH)
    finally:
        model_tmp.unlink(missing_ok=True)
        metrics_tmp.unlink(missing_ok=True)


def train_and_evaluate(
    test_size: float = 0.2,
    random_state: int = 42,
    max_rows: int | None = DEFAULT_MAX_ROWS,
) -> dict:
    """Train a reusable baseline, using a bounded dataset unless asked otherwise."""
    if max_rows is None:
        print("Loading the full GUIDE dataset. This can take a long time and use substantial memory.")
    else:
        print(f"Loading up to {max_rows:,} GUIDE rows for the baseline.")
    raw = load_alerts(nrows=max_rows)
    print("Preprocessing features...")
    X, y, encoders = preprocess(raw)
    print(f"Prepared {len(X):,} alerts with {X.shape[1]} features. Splitting train/test data...")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    clf = RandomForestClassifier(
        n_estimators=0,
        random_state=random_state,
        n_jobs=-1,
        warm_start=True,
    )
    print(f"Training {TOTAL_TREES} Random Forest trees ({TREE_BATCH_SIZE} at a time)...")
    for completed in range(0, TOTAL_TREES, TREE_BATCH_SIZE):
        clf.n_estimators = min(completed + TREE_BATCH_SIZE, TOTAL_TREES)
        clf.fit(X_train, y_train)
        print(f"  trees trained: {clf.n_estimators}/{TOTAL_TREES} ({clf.n_estimators / TOTAL_TREES:.0%})", flush=True)

    print("Scoring holdout set...")
    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    macro_f1 = f1_score(y_test, y_pred, average="macro")

    metrics = {
        "macro_f1": macro_f1,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "classification_report": report,
        "max_rows": max_rows,
        "random_state": random_state,
    }

    # Keep the fitted encoders with the classifier. The RF expects numeric
    # categorical codes, and saving them makes it safe to reuse as the
    # low-context alert fallback rather than refitting encoders at inference.
    _atomically_save(
        {
            "model": clf,
            "encoders": encoders,
            "metadata": expected_metadata(max_rows, test_size, random_state),
        },
        metrics,
    )

    print(f"Macro F1: {macro_f1:.3f}")
    print(classification_report(y_test, y_pred))
    print(f"Metrics saved to {RESULTS_PATH}")
    print(f"Model saved to {MODEL_PATH}")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train or reuse the RF baseline.")
    parser.add_argument("--force-retrain", action="store_true", help="ignore any reusable saved artifact")
    parser.add_argument("--full-data", action="store_true", help="use all GUIDE rows instead of the default 100,000")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, help="rows to use when retraining")
    args = parser.parse_args()

    requested_max_rows = None if args.full_data else args.max_rows
    metadata = expected_metadata(requested_max_rows, 0.2, 42)
    artifact = None if args.force_retrain else load_reusable_artifact(metadata)
    if artifact is None:
        train_and_evaluate(max_rows=requested_max_rows)
    else:
        print("No training or full dataset load was needed.")
