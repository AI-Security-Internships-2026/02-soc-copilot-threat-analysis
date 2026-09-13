"""Issue #41 (M4.4) acceptance criteria: classifier_factory matches the
deployed A4 path exactly, so introducing the abstraction changed nothing.

The RF artifact is gitignored (589 MB), so these are skipped on a fresh
clone rather than failed -- same convention as tests/test_graph_wiring.py's
`requires_model`.
"""

import pytest

from src.agent.fallback_classifier import MODEL_PATH, predict_with_margin
from src.agent.graph import build_triage_graph
from src.models.classifier_factory import load_classifier

requires_model = pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason=(
        f"RF artifact not found at {MODEL_PATH}; run `python -m src.models.baseline` "
        "to train it."
    ),
)

_ALERT = {
    "AlertTitle": 45654,
    "Category": "Execution",
    "MitreTechniques": "T1059.001",
    "LastVerdict": "TruePositive",
    "SuspicionLevel": "Suspicious",
    "DetectorId": 7,
}


@requires_model
def test_load_classifier_succeeds():
    clf = load_classifier()
    assert clf.model_id == "M3a"


@requires_model
def test_predict_proba_shape_matches_three_classes():
    clf = load_classifier()
    probabilities = clf.predict_proba(_ALERT)
    assert probabilities.shape == (3,)
    assert set(clf.classes_) == {"BenignPositive", "FalsePositive", "TruePositive"}
    assert abs(float(probabilities.sum()) - 1.0) < 1e-6


@requires_model
def test_factory_matches_deployed_fallback_classifier_exactly():
    """Same artifact, same tie-break rule -- must agree on every alert."""
    clf = load_classifier()
    label, probability, _margin = predict_with_margin(_ALERT)
    assert clf.predict(_ALERT) == label
    assert abs(float(clf.predict_proba(_ALERT).max()) - probability) < 1e-9


@requires_model
def test_a4_graph_verdict_matches_classifier_factory_directly():
    """No LLM label pollution: the compiled A4 graph must agree with the
    classifier called directly -- the architectural invariant M4.1's ASR
    runner depends on."""
    clf = load_classifier()
    graph = build_triage_graph("rf_primary")
    result = graph.invoke({"raw_alert": _ALERT})
    assert result["predicted_label"] == clf.predict(_ALERT)
