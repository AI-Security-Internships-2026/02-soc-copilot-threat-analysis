"""Tests for the statistical-rigor helpers added in Week 16.

Covers experiments/stats_utils.py (bootstrap CIs, used by
guide_test_holdout_eval.py and roc_auc_analysis.py to replace single-run
point estimates), experiments/roc_auc_analysis.py's compute_ovr_roc_auc
(its own docstring flags getting `classes` out of column order with
proba_matrix as a silent-failure risk -- this pins that it actually fails
loudly/differs, not silently), and experiments/control_node_ablation.py's
error classification, failure histogram, and paired McNemar helper.

All synthetic, deterministic, no live API calls or model artifacts needed.
"""

import numpy as np
import pytest

from experiments.stats_utils import (
    bootstrap_auc_ci,
    bootstrap_metric_ci,
    bootstrap_two_sample_diff_ci,
)
from experiments.roc_auc_analysis import compute_ovr_roc_auc
from experiments.control_node_ablation import (
    _is_quota_error,
    error_histogram,
    paired_mcnemar,
)


def _accuracy(y_true, y_pred):
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    return float((y_true == y_pred).mean())


class TestBootstrapMetricCI:
    def test_perfect_predictions_give_a_degenerate_ci_at_one(self):
        y_true = ["a", "b", "c"] * 20
        y_pred = list(y_true)
        result = bootstrap_metric_ci(y_true, y_pred, _accuracy, n_resamples=500, seed=1)
        assert result["point"] == 1.0
        assert result["ci_lower"] == 1.0
        assert result["ci_upper"] == 1.0

    def test_ci_widens_with_smaller_sample_at_the_same_accuracy(self):
        rng = np.random.default_rng(0)

        def make_sample(n):
            y_true = ["a"] * (n // 2) + ["b"] * (n - n // 2)
            y_pred = list(y_true)
            # flip 20% of predictions so accuracy is 0.8, not degenerate
            flip_idx = rng.choice(n, size=max(1, n // 5), replace=False)
            y_pred = list(y_pred)
            for i in flip_idx:
                y_pred[i] = "b" if y_pred[i] == "a" else "a"
            return y_true, y_pred

        y_true_small, y_pred_small = make_sample(20)
        y_true_large, y_pred_large = make_sample(2000)
        small = bootstrap_metric_ci(y_true_small, y_pred_small, _accuracy, n_resamples=2000, seed=1)
        large = bootstrap_metric_ci(y_true_large, y_pred_large, _accuracy, n_resamples=2000, seed=1)
        small_width = small["ci_upper"] - small["ci_lower"]
        large_width = large["ci_upper"] - large["ci_lower"]
        assert small_width > large_width

    def test_empty_sample_raises_rather_than_returning_a_meaningless_ci(self):
        with pytest.raises(ValueError):
            bootstrap_metric_ci([], [], _accuracy)

    def test_resampling_preserves_pairing_not_independent_shuffles(self):
        # y_true and y_pred must be resampled together (same index each
        # draw) -- resampling them independently would let a row's true
        # label pair with a different row's prediction and produce a
        # meaningless metric distribution.
        y_true = ["a"] * 50 + ["b"] * 50
        y_pred = ["a"] * 50 + ["b"] * 50  # every row correct if paired right
        result = bootstrap_metric_ci(y_true, y_pred, _accuracy, n_resamples=500, seed=3)
        assert result["point"] == 1.0
        assert result["ci_lower"] == 1.0


class TestBootstrapTwoSampleDiffCI:
    def test_identical_distributions_are_not_significant(self):
        rng = np.random.default_rng(0)
        labels = ["a", "b", "c"]
        y_true_a = list(rng.choice(labels, size=300))
        y_pred_a = list(rng.choice(labels, size=300))
        y_true_b = list(rng.choice(labels, size=300))
        y_pred_b = list(rng.choice(labels, size=300))
        result = bootstrap_two_sample_diff_ci(
            y_true_a, y_pred_a, y_true_b, y_pred_b, metric_fn=_accuracy, n_resamples=1000, seed=1
        )
        assert result["ci_lower"] <= 0 <= result["ci_upper"]
        assert result["significant_at_confidence"] is False

    def test_a_clearly_better_than_b_is_significant(self):
        y_true_a = ["a", "b", "c"] * 100
        y_pred_a = list(y_true_a)  # 100% accurate
        y_true_b = ["a", "b", "c"] * 100
        y_pred_b = (["a"] * 100 + ["c"] * 100 + ["a"] * 100)  # roughly chance-level
        result = bootstrap_two_sample_diff_ci(
            y_true_a, y_pred_a, y_true_b, y_pred_b, metric_fn=_accuracy, n_resamples=1000, seed=1
        )
        assert result["point_diff"] > 0
        assert result["ci_lower"] > 0
        assert result["significant_at_confidence"] is True

    def test_empty_sample_raises(self):
        with pytest.raises(ValueError):
            bootstrap_two_sample_diff_ci([], [], ["a"], ["a"], metric_fn=_accuracy)


class TestBootstrapAucCI:
    def test_perfect_separation_gives_auc_near_one(self):
        classes = ["a", "b", "c"]
        y_true = ["a"] * 30 + ["b"] * 30 + ["c"] * 30
        proba = np.zeros((90, 3))
        for i, label in enumerate(y_true):
            proba[i, classes.index(label)] = 1.0
        result = bootstrap_auc_ci(y_true, proba, classes=classes, n_resamples=200, seed=1)
        assert result["point"] == 1.0
        assert result["ci_lower"] is not None
        assert result["ci_lower"] > 0.9

    def test_resamples_missing_a_class_are_skipped_not_fatal(self):
        # Tiny, heavily imbalanced sample makes it likely some bootstrap
        # resamples drop a class entirely -- must not raise.
        classes = ["a", "b", "c"]
        y_true = ["a"] * 8 + ["b"] * 1 + ["c"] * 1
        proba = np.array([[0.8, 0.1, 0.1]] * 8 + [[0.2, 0.7, 0.1]] + [[0.2, 0.1, 0.7]])
        result = bootstrap_auc_ci(y_true, proba, classes=classes, n_resamples=300, seed=1)
        assert result["point"] is not None
        assert result["resamples_skipped"] >= 0


class TestComputeOvrRocAuc:
    def test_matches_sklearn_reference_for_perfect_classifier(self):
        classes = ["a", "b", "c"]
        y_true = ["a", "b", "c"] * 10
        proba = np.zeros((30, 3))
        for i, label in enumerate(y_true):
            proba[i, classes.index(label)] = 1.0
        result = compute_ovr_roc_auc(y_true, proba, classes=classes)
        assert result["macro_auc"] == 1.0
        for cls in classes:
            assert result["per_class"][cls]["auc"] == 1.0

    def test_column_order_mismatch_silently_changes_the_result(self):
        # This is the exact silent-failure risk the script's own docstring
        # warns about: `classes` must be in the SAME COLUMN ORDER as
        # proba_matrix. sklearn's roc_auc_score itself only validates that
        # the `labels` list is alphabetically sorted -- it has no way to
        # know whether proba_matrix's columns actually correspond to that
        # order, so a caller that builds proba_matrix in a different column
        # order than `classes` gets no error, just a wrong number. `classes`
        # stays validly sorted in both cases here (["a","b","c"]); what
        # differs is which column of proba_matrix each row's probability
        # mass was put in -- the exact caller-side bug the docstring warns
        # about, not an sklearn-rejected input.
        classes = ["a", "b", "c"]
        y_true = ["a"] * 20 + ["b"] * 20 + ["c"] * 20

        proba_correct = np.zeros((60, 3))
        for i, label in enumerate(y_true):
            proba_correct[i, classes.index(label)] = 0.9
            for j in range(3):
                if j != classes.index(label):
                    proba_correct[i, j] = 0.05

        # Same probabilities, but columns 0 and 1 (a and b) are swapped --
        # simulates proba_matrix being built in a different column order
        # than `classes` claims.
        proba_mismatched = proba_correct[:, [1, 0, 2]]

        correct = compute_ovr_roc_auc(y_true, proba_correct, classes=classes)
        mismatched = compute_ovr_roc_auc(y_true, proba_mismatched, classes=classes)
        assert correct["macro_auc"] != mismatched["macro_auc"]
        assert correct["per_class"]["a"]["auc"] != mismatched["per_class"]["a"]["auc"]


class TestIsQuotaError:
    @pytest.mark.parametrize(
        "message",
        [
            "Error code: 429 - rate_limit_exceeded",
            "RateLimitError: quota exceeded for openai/gpt-oss-20b",
            "insufficient_quota: you have used all available tokens",
        ],
    )
    def test_recognises_quota_errors(self, message):
        assert _is_quota_error(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Connection reset by peer",
            "ReadTimeout: request timed out after 30s",
            "KeyError: 'predicted_label'",
        ],
    )
    def test_does_not_flag_transient_or_unrelated_errors_as_quota(self, message):
        assert _is_quota_error(message) is False


class TestErrorHistogram:
    def test_groups_scored_rows_out_and_buckets_by_error_type(self):
        rows = [
            {"predicted_label": "TruePositive", "error": None},
            {"predicted_label": None, "error": "Error code: 429 - rate_limit_exceeded"},
            {"predicted_label": None, "error": "Error code: 429 - rate_limit_exceeded"},
            {"predicted_label": None, "error": "Connection reset by peer"},
            {"predicted_label": None, "error": None},
        ]
        hist = error_histogram(rows)
        assert hist["n_unscored"] == 4
        assert hist["n_quota_exhaustion"] == 2
        assert hist["n_other_error"] == 1
        assert hist["n_unscored_no_error_string"] == 1
        assert sum(hist["quota_error_messages"].values()) == 2
        assert sum(hist["other_error_messages"].values()) == 1

    def test_no_unscored_rows_gives_a_clean_zero_histogram(self):
        rows = [{"predicted_label": "TruePositive", "error": None}] * 5
        hist = error_histogram(rows)
        assert hist["n_unscored"] == 0
        assert hist["quota_error_messages"] == {}


class TestPairedMcnemar:
    def test_restricted_to_rows_scored_by_both_arms(self):
        rows_a = [
            {"_row_index": 1, "ground_truth": "x", "predicted_label": "x"},
            {"_row_index": 2, "ground_truth": "x", "predicted_label": "y"},
            {"_row_index": 3, "ground_truth": "x", "predicted_label": "x"},
        ]
        # row 3 unscored in the other arm -- must be excluded from the pairing
        rows_other = [
            {"_row_index": 1, "ground_truth": "x", "predicted_label": "y"},
            {"_row_index": 2, "ground_truth": "x", "predicted_label": "y"},
            {"_row_index": 3, "ground_truth": "x", "predicted_label": None},
        ]
        result = paired_mcnemar(rows_a, rows_other)
        assert result["n_paired"] == 2

    def test_no_overlap_reports_zero_paired_not_a_crash(self):
        rows_a = [{"_row_index": 1, "ground_truth": "x", "predicted_label": "x"}]
        rows_other = [{"_row_index": 99, "ground_truth": "x", "predicted_label": "x"}]
        result = paired_mcnemar(rows_a, rows_other)
        assert result["n_paired"] == 0
        assert "note" in result
