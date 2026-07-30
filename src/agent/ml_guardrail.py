"""Model-based second-stage guardrail, sitting behind the regex fast-path.

The regex guardrail (guardrails.py) catches fixed phrasing fast and cheap,
but paraphrasing or encoding can slip past it. This runs alert text through
a small ML classifier instead, which generalises past exact wording.

Model: reused from 03-prompt-injection-detection's TF-IDF + Logistic
Regression detector (see experiments/models/). Chosen over Llama Prompt
Guard / LLM Guard after benchmarking (issue #10) showed this detector beats
both on F1 (0.88 vs 0.75/0.72) *and* is ~225x faster (0.8ms vs ~180ms median
latency) -- see guardrail_comparison.json in that repo for the full numbers.
"""

from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "experiments" / "models"
VECTORIZER_PATH = MODEL_DIR / "vectorizer.pkl"
CLASSIFIER_PATH = MODEL_DIR / "classifier.pkl"

# score above this = flagged for human review.
FLAG_THRESHOLD = 0.5


@lru_cache(maxsize=1)
def _get_detector():
    """Load the vectorizer + classifier once and cache them."""
    with open(VECTORIZER_PATH, "rb") as f:
        vectorizer = pickle.load(f)
    with open(CLASSIFIER_PATH, "rb") as f:
        classifier = pickle.load(f)
    return vectorizer, classifier


def score_text(text: str) -> float:
    """Return a 0-1 'prompt injection' probability for one string.

    Returns 0.0 for empty/non-string input instead of raising -- alert
    fields are often missing, and this guardrail should never be the
    reason the pipeline crashes.
    """
    if not text or not isinstance(text, str):
        return 0.0

    vectorizer, classifier = _get_detector()
    X = vectorizer.transform([text])

    if hasattr(classifier, "predict_proba"):
        return float(classifier.predict_proba(X)[0][1])
    # fallback if the pickled model has no predict_proba for some reason
    return float(classifier.predict(X)[0])


# fields worth ML-checking for injection risk — mirrors the regex guardrail's
# own reasoning that free text (not structured categorical fields) is the risk
ML_CHECKED_FIELDS = {"AlertTitle"}

def inspect_alert_ml(alert: dict[str, Any]) -> list[tuple[str, float]]:
    flagged = []
    for field, value in alert.items():
        if field not in ML_CHECKED_FIELDS or not isinstance(value, str):
            continue
        score = score_text(value)
        if score >= FLAG_THRESHOLD:
            flagged.append((field, score))
    return flagged