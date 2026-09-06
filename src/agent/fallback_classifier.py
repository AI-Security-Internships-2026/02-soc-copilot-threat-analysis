"""The trained Random Forest classifier that decides every alert's verdict.

Until Week 15 this was a narrow fallback: the pipeline sent well-evidenced
alerts to the LLM and used this model only for sparse ones. Week 15's control
experiment (experiments/rf_vs_llm_control.py) scored both models on the exact
same 209 well-evidenced alerts -- the ones the router had been sending to the
LLM -- and removed the confound that had made the comparison unreadable:

    RandomForest   accuracy 0.6555   macro F1 0.6035
    LLM            accuracy 0.2823   macro F1 0.2121
    always-guess-BenignPositive      0.4928

The LLM scored 21 points below a constant answer on the alerts specifically
chosen as its best case, and the RF beat it on 105 of the 132 alerts where
exactly one of them was right (exact McNemar p = 4.7e-12). Those alerts were
not intrinsically hard; the LLM was simply worse at this task.

So label authority moved here, and the LLM moved to writing the analyst-facing
explanation. The name of this module is kept for continuity with the Weeks 6-14
results files that reference it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.data.preprocess import transform_with_encoders


MODEL_PATH = Path("experiments/results/baseline_model.joblib")

# These are the fields that carry analyst-readable evidence in the current
# prompt. AlertTitle/Category alone are often numeric GUIDE codes, so they do
# not make an alert high-context by themselves.
EVIDENCE_FIELDS = ("MitreTechniques", "SuspicionLevel", "LastVerdict")


def _present(value: Any) -> bool:
    """Return whether a value is present while treating 0 as a valid code."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return not pd.isna(value)


def evidence_field_count(alert: dict[str, Any]) -> int:
    """Count populated discriminative fields used to decide the route."""
    return sum(_present(alert.get(field)) for field in EVIDENCE_FIELDS)


def should_use_fallback(alert: dict[str, Any]) -> bool:
    """Use RF only when fewer than two discriminative evidence fields exist."""
    return evidence_field_count(alert) < 2


@lru_cache(maxsize=1)
def _load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Fallback model not found at {MODEL_PATH}")
    artifact = joblib.load(MODEL_PATH)
    if not isinstance(artifact, dict) or {"model", "encoders"} - artifact.keys():
        raise ValueError(
            "Fallback model is a legacy artifact without saved encoders. "
            "Run `python -m src.models.baseline` to create the reusable artifact."
        )
    return artifact


def _model_features(model) -> list[str]:
    features = getattr(model, "feature_names_in_", None)
    if features is None:
        raise ValueError("Fallback model has no saved feature names.")
    return list(features)


def _to_feature_frame(alert: dict[str, Any], model, encoders: dict) -> pd.DataFrame:
    """Recreate the baseline's timestamp features and exact feature order."""
    row = dict(alert)
    timestamp = pd.to_datetime(row.get("Timestamp"), errors="coerce", utc=True)
    row["Hour"] = timestamp.hour if not pd.isna(timestamp) else row.get("Hour")
    row["DayOfWeek"] = timestamp.dayofweek if not pd.isna(timestamp) else row.get("DayOfWeek")
    row["Month"] = timestamp.month if not pd.isna(timestamp) else row.get("Month")
    frame = pd.DataFrame([row])
    frame = transform_with_encoders(frame, encoders)
    return frame.reindex(columns=_model_features(model))


def predict_with_fallback(alert: dict[str, Any]) -> tuple[str, float]:
    """Return the RF label and its maximum class probability for one alert."""
    label, probability, _ = predict_with_margin(alert)
    return label, probability


def predict_with_margin(alert: dict[str, Any]) -> tuple[str, float, float]:
    """Return the RF label, its top-1 probability, and its decision margin.

    The margin is top-1 minus top-2 probability, and it is the quantity the
    pipeline gates human review on (Week 15). Max probability alone cannot
    distinguish a genuine call from a coin flip: 0.45 with a 0.44 runner-up is
    a near-tie, while 0.45 with a 0.10 runner-up is decisive, yet both look
    identical to a threshold on max probability.

    Week 15 measured both signals on the same 209 alerts
    (experiments/rf_vs_llm_control.py). Accuracy among auto-accepted alerts
    rises monotonically with this margin -- 0.648 at a 0.05 threshold through
    0.761 at 0.50 -- so it is a usable confidence signal. The LLM's own
    self-reported confidence was inverted over the same alerts (0.256 accurate
    when it said "high" versus 0.383 when it said "medium"), which is why
    label authority and the review gate both moved to the RF.
    """
    artifact = _load_model()
    model = artifact["model"]
    features = _to_feature_frame(alert, model, artifact["encoders"])
    probabilities = model.predict_proba(features)[0]
    order = np.argsort(probabilities)[::-1]
    label = str(model.classes_[order[0]])
    top1 = float(probabilities[order[0]])
    top2 = float(probabilities[order[1]]) if len(probabilities) > 1 else 0.0
    return label, top1, top1 - top2
