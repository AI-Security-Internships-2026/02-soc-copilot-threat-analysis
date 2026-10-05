"""Issue #41 (M4.4) acceptance criteria: classifier_factory matches the
deployed A4 path exactly, so introducing the abstraction changed nothing.

The RF artifact is gitignored (589 MB), so these are skipped on a fresh
clone rather than failed -- same convention as tests/test_graph_wiring.py's
`requires_model`.
"""

from pathlib import Path

import pytest

from src.agent.fallback_classifier import MODEL_PATH, predict_with_margin
from src.agent.graph import build_triage_graph
from src.models.classifier_factory import load_classifier, to_feature_frame

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


_STUDY_SAMPLE = Path("experiments/results/m4_3_study_alerts.csv")
_DERIVED = {"item_id", "ground_truth", "rf_verdict", "rf_probability", "rf_margin"}


@requires_model
@pytest.mark.skipif(
    not _STUDY_SAMPLE.exists(),
    reason="m4_3_study_alerts.csv not generated -- run m4_3_build_human_study_package.py --sample",
)
def test_factory_agrees_with_the_deployed_path_over_a_real_sample():
    """One alert is not enough to license the rewiring.

    `predict_with_margin` routes through `load_classifier()` now (issue #41).
    The factory's own `predict_proba` used to carry a second, weaker copy of the
    feature-alignment logic -- it was missing the object-column coercion, which
    is what made a full synthetic Wazuh row raise on 'DEVICE-96' in M5.2. They
    share one implementation now, and this pins them agreeing bit-for-bit over
    100 real GUIDE rows rather than one hand-written alert.
    """
    import pandas as pd

    clf = load_classifier()
    rows = pd.read_csv(_STUDY_SAMPLE, low_memory=False).to_dict("records")
    assert len(rows) == 100
    for row in rows:
        alert = {k: v for k, v in row.items() if k not in _DERIVED and pd.notna(v)}
        label, probability, _margin = predict_with_margin(alert)
        assert clf.predict(alert) == label, f"{row['item_id']}: label disagrees"
        assert abs(float(clf.predict_proba(alert).max()) - probability) < 1e-12


@requires_model
def test_predict_with_margin_reads_the_artifact_through_the_factory():
    """Mati's #41 item 1: the deployed path must not keep its own loader.

    Asserted on identity, not on behaviour -- a second `joblib.load` of the same
    file would pass any numeric comparison while leaving the separate path in
    place, which is exactly what the issue asked to remove.
    """
    from src.agent import fallback_classifier

    assert fallback_classifier._load_model()["model"] is load_classifier().model
    assert fallback_classifier.to_feature_frame is to_feature_frame


@requires_model
def test_a4_graph_verdict_matches_classifier_factory_directly():
    """No LLM label pollution: the compiled A4 graph must agree with the
    classifier called directly -- the architectural invariant M4.1's ASR
    runner depends on."""
    clf = load_classifier()
    graph = build_triage_graph("rf_primary")
    result = graph.invoke({"raw_alert": _ALERT})
    assert result["predicted_label"] == clf.predict(_ALERT)
