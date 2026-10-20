"""Issue #41 (M4.4): a named, swappable seam for "the deployed classifier".

`src/agent/fallback_classifier.py` already isolates the artifact-loading and
feature-alignment logic behind `predict_with_margin()` -- this module does not
duplicate that. What was missing was a place that says *which* model backs the
A4 pipeline, keyed to the two decisions that actually determine it:

  - M2.4 (experiments/results/m2_4_best_model_selection.json): auto-selected
    "M3a" (plain RandomForestClassifier(200), LabelEncoder categoricals) as
    the best of 7 classifier families.
  - M2.3 (docs/m2-3-deploy-decision-memo.md): KEEP the current 100K-row
    `experiments/results/baseline_model.joblib` through M2-M5; the 500K-row,
    GroupShuffleSplit-trained candidate (`models/best_grouped_classifier.joblib`,
    real and scored, +2.96/+6.31 points) is deferred to a single deliberate
    swap at M6, bundled with the final reproducibility pass, so no published
    number moves mid-schedule.

Net effect right now: MODEL_ID == "M3a" == what `fallback_classifier.py`
already loads. There is no swap to perform today, so `graph.py`'s
`classify_with_rf` node is deliberately left untouched -- renaming or
rewiring a stable, tested production path for a model that is not changing
would be churn, not integration work. What this module adds is the seam:
a single named constant and loader that M4.1's ASR runner and the eventual
M6 swap both read, instead of each call site re-deriving "which model" on
its own.

When M6 adopts the grouped model, add its case to `_ARTIFACT_PATHS` /
`_BACKENDS` and flip `MODEL_ID` -- everything reading through
`load_classifier()` picks it up without further changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.data.preprocess import transform_with_encoders
from src.models.decision import resolve_label

#: M2.4's auto-selected best tabular classifier, as recorded in
#: experiments/results/m2_4_best_model_selection.json ("selected": "M3a").
MODEL_ID = "M3a"

#: model_id -> artifact path. Only M3a is implemented: it is the only model
#: id the M2.3 decision memo currently authorizes for deployment. Other ids
#: raise NotImplementedError with a pointer to the memo rather than silently
#: falling back to M3a, so a future swap can't be masked by a typo'd id.
_ARTIFACT_PATHS = {
    "M3a": Path("experiments/results/baseline_model.joblib"),
}


def _model_features(model) -> list[str]:
    features = getattr(model, "feature_names_in_", None)
    if features is None:
        raise ValueError("Classifier artifact has no saved feature names.")
    return list(features)


def to_feature_frame(alert: dict[str, Any], model, encoders: dict) -> pd.DataFrame:
    """Recreate the baseline's timestamp features and exact feature order."""
    row = dict(alert)
    timestamp = pd.to_datetime(row.get("Timestamp"), errors="coerce", utc=True)
    row["Hour"] = timestamp.hour if not pd.isna(timestamp) else row.get("Hour")
    row["DayOfWeek"] = timestamp.dayofweek if not pd.isna(timestamp) else row.get("DayOfWeek")
    row["Month"] = timestamp.month if not pd.isna(timestamp) else row.get("Month")
    frame = pd.DataFrame([row])
    frame = transform_with_encoders(frame, encoders)
    frame = frame.reindex(columns=_model_features(model))

    # transform_with_encoders only touches columns that had a LabelEncoder
    # saved at train time (encode_categoricals only fits one for columns
    # pandas inferred as dtype "object" in the training data). A feature like
    # DeviceName is numeric in GUIDE's real schema, so it has no encoder --
    # but a caller can still hand this function an unexpected string for it
    # (e.g. a real-world hostname, or a synthetic test alert). Left alone
    # that string reaches model.predict_proba() as-is and crashes the whole
    # triage graph on a ValueError, turning "one weird field" into "no
    # verdict for this alert at all". Coerce it to NaN instead, the same
    # "unknown -> missing" treatment transform_with_encoders already gives an
    # out-of-vocabulary value in an *encoded* column.
    unencoded_object_cols = [c for c in frame.select_dtypes(include="object").columns if c not in encoders]
    if unencoded_object_cols:
        frame[unencoded_object_cols] = frame[unencoded_object_cols].apply(pd.to_numeric, errors="coerce")
    return frame


@dataclass(frozen=True)
class Classifier:
    """Backend-agnostic view over a trained tabular classifier artifact.

    Exposes exactly the two operations callers need (predict_proba on a raw
    alert dict, and the resulting label via the project's shared tie-break
    rule) without leaking the artifact's internal shape.
    """

    model_id: str
    model: Any
    encoders: dict

    def predict_proba(self, alert: dict[str, Any]) -> np.ndarray:
        frame = to_feature_frame(alert, self.model, self.encoders)
        return self.model.predict_proba(frame)[0]

    def predict(self, alert: dict[str, Any]) -> str:
        probabilities = self.predict_proba(alert)
        return resolve_label(self.model.classes_, probabilities)

    @property
    def classes_(self):
        return self.model.classes_


@lru_cache(maxsize=None)
def load_classifier(model_id: str = MODEL_ID) -> Classifier:
    """Load the classifier `model_id` currently authorized for deployment.

    Cached per model_id (mirrors fallback_classifier.py's single-artifact
    cache) so repeated calls -- e.g. once per alert in an evaluation loop --
    don't re-read the joblib file from disk.
    """
    if model_id not in _ARTIFACT_PATHS:
        raise NotImplementedError(
            f"classifier_factory has no backend for model_id={model_id!r}. "
            "Only 'M3a' is authorized for deployment right now -- see "
            "docs/m2-3-deploy-decision-memo.md for the ADOPT vs KEEP call "
            "that gates adding another id here."
        )
    path = _ARTIFACT_PATHS[model_id]
    if not path.exists():
        raise FileNotFoundError(f"Classifier artifact not found at {path}")
    artifact = joblib.load(path)
    if not isinstance(artifact, dict) or {"model", "encoders"} - artifact.keys():
        raise ValueError(f"{path} is not a {{'model', 'encoders'}} artifact dict")
    return Classifier(model_id=model_id, model=artifact["model"], encoders=artifact["encoders"])
