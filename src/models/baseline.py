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

import json
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split

from src.data.load_data import load_alerts
from src.data.preprocess import preprocess

RESULTS_PATH = Path("experiments/results/baseline_metrics.json")
MODEL_PATH = Path("experiments/results/baseline_model.joblib")


def train_and_evaluate(test_size: float = 0.2, random_state: int = 42) -> dict:
    raw = load_alerts()
    X, y, _ = preprocess(raw)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    clf = RandomForestClassifier(n_estimators=200, random_state=random_state, n_jobs=-1)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    macro_f1 = f1_score(y_test, y_pred, average="macro")

    metrics = {
        "macro_f1": macro_f1,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "classification_report": report,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    joblib.dump(clf, MODEL_PATH)

    print(f"Macro F1: {macro_f1:.3f}")
    print(classification_report(y_test, y_pred))
    print(f"Metrics saved to {RESULTS_PATH}")
    print(f"Model saved to {MODEL_PATH}")

    return metrics


if __name__ == "__main__":
    train_and_evaluate()
