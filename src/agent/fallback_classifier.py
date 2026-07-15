"""Low-context fallback to the trained Random Forest baseline.

The LLM is useful when an alert contains analyst-readable evidence.  GUIDE
alerts with most of that evidence missing are different: categorical values are
numeric dataset codes, so an LLM has little basis for a per-alert judgement.
For that narrow case, use the already-trained structured-data classifier.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
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
    artifact = _load_model()
    model = artifact["model"]
    features = _to_feature_frame(alert, model, artifact["encoders"])
    label = str(model.predict(features)[0])
    probability = float(model.predict_proba(features)[0].max())
    return label, probability
