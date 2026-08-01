"""Regression test for src/agent/ml_guardrail.py.

Week 8's review (docs/weekly-progress.md) caught score_text() reading
predict_proba(X)[0][0] (P(benign)) instead of [0][1] (P(injection)) --
exactly backwards. Fixed by flipping the index. This pins that fix so the
same class of silent-direction bug can't reappear unnoticed; it does not
depend on the real pickled model, so it stays fast and deterministic.
"""

import src.agent.ml_guardrail as ml_guardrail


class _FakeClassifier:
    """classes_ = [0=Benign, 1=Prompt Injection Attack], per ml_detector.py's
    own docstring (referenced in ml_guardrail.py's module docstring)."""

    def predict_proba(self, X):
        # deliberately asymmetric so [0][0] vs [0][1] can't accidentally agree
        return [[0.1, 0.9]]


class _FakeVectorizer:
    def transform(self, texts):
        return texts


def test_score_text_reads_the_injection_class_probability(monkeypatch):
    monkeypatch.setattr(
        ml_guardrail,
        "_get_detector",
        lambda: (_FakeVectorizer(), _FakeClassifier()),
    )

    score = ml_guardrail.score_text("some alert text")

    assert score == 0.9, (
        f"expected P(injection) = predict_proba(X)[0][1] = 0.9, got {score} -- "
        "looks like the [0][0]/[0][1] index bug regressed"
    )


def test_score_text_handles_empty_and_non_string_input():
    assert ml_guardrail.score_text("") == 0.0
    assert ml_guardrail.score_text(None) == 0.0
    assert ml_guardrail.score_text(12345) == 0.0
