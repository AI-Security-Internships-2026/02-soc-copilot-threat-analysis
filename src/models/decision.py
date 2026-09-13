"""How a probability vector becomes a verdict -- defined once, in one place.

Turning `predict_proba` output into a label looks like a detail with one
obvious implementation, and it is not: the two obvious implementations disagree
whenever the top two classes tie, and this repository shipped both.

    np.argmax(p)              -> the FIRST maximal index
    np.argsort(p)[::-1][0]    -> the LAST maximal index

With `classes_` in sklearn's sorted order -- BenignPositive, FalsePositive,
TruePositive -- those resolve a tie in opposite directions: `argmax` toward
BenignPositive, `argsort` toward TruePositive.

Ties are not hypothetical here. A 200-tree forest voting on three classes
produces exact ties on 0.1-0.2% of alerts (32 of the 15,000 held-out rows), and
Week 17 measured what the disagreement is worth:

    held-out GUIDE_Test n=15,000   argmax 0.6993 / argsort 0.6998
    train-sampled n=999            argmax 0.7337 / argsort 0.7347

Every published figure in this project was computed under the `argsort` rule --
it is what `src/agent/fallback_classifier.py` has always used on the deployed
path, so it is the behaviour the system actually has. This module makes that
rule explicit and shared rather than re-derived per call site, so the
evaluation harness and the deployed path cannot drift apart.

The rule preserved here is "on a tie, prefer the later class in `classes_`
order". That is an accident of alphabetical ordering rather than a designed
severity preference, and it is documented as such: it is kept because changing
it would silently move every published number, not because ranking
TruePositive above FalsePositive above BenignPositive is principled.
"""

from __future__ import annotations

import numpy as np

#: Which end of a tie wins. Kept as a named constant so the choice is greppable.
TIE_BREAK = "last-class-in-classes_-order"


def resolve_index(probabilities) -> int:
    """Index of the winning class for one probability vector."""
    return int(np.argsort(np.asarray(probabilities))[::-1][0])


def resolve_label(classes, probabilities) -> str:
    """Winning class label for one probability vector."""
    return str(classes[resolve_index(probabilities)])


def resolve_labels(classes, probability_matrix) -> np.ndarray:
    """Winning class label for each row of a (n_samples, n_classes) matrix.

    Equivalent to calling resolve_label() per row, and unlike
    ``estimator.predict()`` it applies this module's tie-break rather than
    sklearn's internal argmax.
    """
    matrix = np.asarray(probability_matrix)
    indices = (matrix.shape[1] - 1) - np.argmax(matrix[:, ::-1], axis=1)
    return np.asarray(classes)[indices]


def predict_labels(estimator, X) -> np.ndarray:
    """Predict labels for X under this module's tie-break rule."""
    return resolve_labels(estimator.classes_, estimator.predict_proba(X))
