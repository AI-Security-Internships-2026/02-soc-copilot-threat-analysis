"""The tie-break rule is a published-number dependency, so it is pinned here.

Week 17 found the repository resolving `predict_proba` ties two different ways
in two different files -- `np.argmax` in the leakage audit, `np.argsort(...)[::-1]`
on the deployed path and in every experiment that produced a published figure.
The two disagree on 0.1-0.2% of alerts, which is worth 0.0005 accuracy on the
held-out split. These tests exist so the rule cannot drift again silently.
"""

import numpy as np
import pytest

from src.models.decision import predict_labels, resolve_index, resolve_label, resolve_labels

CLASSES = np.array(["BenignPositive", "FalsePositive", "TruePositive"])


def _argsort_reference(classes, probabilities):
    """The literal expression every published figure was computed with."""
    return str(classes[int(np.argsort(probabilities)[::-1][0])])


@pytest.mark.parametrize(
    "probabilities, expected",
    [
        ([0.1, 0.2, 0.7], "TruePositive"),      # no tie
        ([0.7, 0.2, 0.1], "BenignPositive"),    # no tie
        ([0.5, 0.5, 0.0], "FalsePositive"),     # tie -> later class wins
        ([0.0, 0.5, 0.5], "TruePositive"),      # tie -> later class wins
        ([0.5, 0.0, 0.5], "TruePositive"),      # tie across a gap
        ([1 / 3, 1 / 3, 1 / 3], "TruePositive"),  # three-way tie
    ],
)
def test_ties_resolve_toward_the_later_class(probabilities, expected):
    assert resolve_label(CLASSES, probabilities) == expected


@pytest.mark.parametrize(
    "probabilities",
    [
        [0.1, 0.2, 0.7], [0.5, 0.5, 0.0], [0.0, 0.5, 0.5],
        [0.34, 0.33, 0.33], [0.25, 0.5, 0.25], [1 / 3, 1 / 3, 1 / 3],
    ],
)
def test_matches_the_expression_published_figures_used(probabilities):
    assert resolve_label(CLASSES, probabilities) == _argsort_reference(CLASSES, probabilities)


def test_the_rule_actually_differs_from_argmax_on_a_tie():
    """If this ever passes trivially, the two rules have converged and the
    documented 0.0005 discrepancy no longer exists."""
    tied = [0.5, 0.5, 0.0]
    assert resolve_label(CLASSES, tied) != str(CLASSES[int(np.argmax(tied))])


def test_vectorised_form_matches_the_per_row_form():
    rng = np.random.default_rng(42)
    rows = rng.integers(0, 5, size=(500, 3)) / 4.0  # coarse grid, so ties are common
    rows = rows / np.clip(rows.sum(axis=1, keepdims=True), 1e-9, None)
    assert list(resolve_labels(CLASSES, rows)) == [resolve_label(CLASSES, r) for r in rows]


def test_predict_labels_uses_the_rule_not_sklearn_argmax():
    class TiedEstimator:
        classes_ = CLASSES

        def predict_proba(self, X):
            return np.array([[0.5, 0.5, 0.0], [0.0, 0.5, 0.5]])

    assert list(predict_labels(TiedEstimator(), None)) == ["FalsePositive", "TruePositive"]


def test_resolve_index_returns_a_plain_int():
    assert isinstance(resolve_index([0.2, 0.3, 0.5]), int)
