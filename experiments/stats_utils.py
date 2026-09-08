# experiments/stats_utils.py
#
# Shared statistical-rigor helpers for the paper's evaluation scripts.
#
# Every accuracy/F1/AUC figure reported so far (guide_test_holdout_eval.py,
# roc_auc_analysis.py, control_node_ablation.py) is a single-run point
# estimate -- the paper's own Limitations section says so explicitly
# ("Results are single-run point estimates without confidence intervals").
# This module is what closes that gap: percentile-bootstrap confidence
# intervals for a metric on one sample, and for the *difference* between two
# independent samples (e.g. held-out vs train-sampled accuracy, which are
# scored on different alerts and so are not a paired comparison -- McNemar's
# test, used elsewhere in this project for same-row paired comparisons,
# doesn't apply here).
#
# McNemar's exact test itself is NOT duplicated here: experiments/
# rf_vs_llm_control.py already has mcnemar(), and other scripts import it
# directly (see control_node_ablation.py) rather than each script keeping
# its own copy.
#
# Week 18 (M2.1/M2.4, issues #31/#34) added three more general-purpose tests
# that nothing in the repo had needed before: Wilcoxon signed-rank (paired
# per-seed deltas, e.g. row-split-minus-group-split accuracy across 5 seeds),
# Pearson correlation (the overlap-vs-inflation scatter), and Cochran's Q
# (omnibus test across more than two classifiers' per-item correct/incorrect
# calls -- McNemar only handles a pair). Cochran's Q has no scipy
# implementation and this project does not depend on statsmodels for one
# formula, so it's computed directly from its standard definition.

from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats


def bootstrap_metric_ci(
    y_true: list,
    y_pred: list,
    metric_fn,
    n_resamples: int = 10_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict:
    """Percentile bootstrap CI for a metric computed on one paired sample.

    Resamples (y_true[i], y_pred[i]) pairs with replacement -- not y_true and
    y_pred independently, which would break the pairing and produce a
    meaningless metric. `metric_fn(y_true_arr, y_pred_arr) -> float`.
    """
    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)
    n = len(y_true_arr)
    if n == 0:
        raise ValueError("bootstrap_metric_ci: empty sample")

    point = float(metric_fn(y_true_arr, y_pred_arr))
    rng = np.random.default_rng(seed)
    resample_stats = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.integers(0, n, n)
        resample_stats[i] = metric_fn(y_true_arr[idx], y_pred_arr[idx])

    alpha = (1 - confidence) / 2
    lower, upper = np.quantile(resample_stats, [alpha, 1 - alpha])
    return {
        "point": round(point, 4),
        "ci_lower": round(float(lower), 4),
        "ci_upper": round(float(upper), 4),
        "confidence": confidence,
        "n": n,
        "n_resamples": n_resamples,
        "method": "percentile bootstrap, resampling paired (y_true, y_pred) rows with replacement",
    }


def bootstrap_auc_ci(
    y_true: list,
    proba_matrix: np.ndarray,
    classes: list,
    n_resamples: int = 2_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict:
    """Percentile bootstrap CI for macro one-vs-rest ROC/AUC.

    Fewer resamples than bootstrap_metric_ci (2,000 vs 10,000) because
    roc_auc_score(multi_class="ovr") is materially more expensive per call;
    2,000 is still enough for a stable percentile estimate at this sample
    size. A resample that happens to drop every example of one class is
    skipped (AUC undefined for a class with zero positives or zero
    negatives) rather than allowed to raise and abort the whole run --
    tracked and reported as `resamples_skipped`.
    """
    from sklearn.metrics import roc_auc_score

    y_true_arr = np.asarray(y_true)
    proba = np.asarray(proba_matrix)
    n = len(y_true_arr)
    if n == 0:
        raise ValueError("bootstrap_auc_ci: empty sample")

    point = float(
        roc_auc_score(y_true_arr, proba, multi_class="ovr", average="macro", labels=list(classes))
    )
    rng = np.random.default_rng(seed)
    resample_stats = []
    skipped = 0
    for _ in range(n_resamples):
        idx = rng.integers(0, n, n)
        y_resampled = y_true_arr[idx]
        if len(set(y_resampled)) < len(classes):
            skipped += 1
            continue
        try:
            resample_stats.append(
                roc_auc_score(
                    y_resampled, proba[idx], multi_class="ovr", average="macro", labels=list(classes)
                )
            )
        except ValueError:
            skipped += 1

    if not resample_stats:
        return {
            "point": round(point, 4),
            "ci_lower": None,
            "ci_upper": None,
            "confidence": confidence,
            "n": n,
            "n_resamples": n_resamples,
            "resamples_skipped": skipped,
            "method": "percentile bootstrap on macro one-vs-rest AUC; every resample lacked full class coverage",
        }

    alpha = (1 - confidence) / 2
    lower, upper = np.quantile(resample_stats, [alpha, 1 - alpha])
    return {
        "point": round(point, 4),
        "ci_lower": round(float(lower), 4),
        "ci_upper": round(float(upper), 4),
        "confidence": confidence,
        "n": n,
        "n_resamples": len(resample_stats),
        "resamples_skipped": skipped,
        "method": "percentile bootstrap, resampling rows (with their full probability vectors) with replacement",
    }


def bootstrap_two_sample_diff_ci(
    y_true_a: list,
    y_pred_a: list,
    y_true_b: list,
    y_pred_b: list,
    metric_fn,
    n_resamples: int = 10_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict:
    """Percentile bootstrap CI on metric(a) - metric(b) for two INDEPENDENT samples.

    Use this, not McNemar's test, when a and b are different rows (e.g. a
    held-out split vs. a train-sampled split) rather than the same rows
    scored two ways. Resamples a and b independently each iteration. If the
    resulting CI excludes 0, the gap is a real effect at this confidence
    level rather than sampling noise; if it includes 0, it isn't
    distinguishable from noise at this sample size.
    """
    y_true_a_arr, y_pred_a_arr = np.asarray(y_true_a), np.asarray(y_pred_a)
    y_true_b_arr, y_pred_b_arr = np.asarray(y_true_b), np.asarray(y_pred_b)
    n_a, n_b = len(y_true_a_arr), len(y_true_b_arr)
    if n_a == 0 or n_b == 0:
        raise ValueError("bootstrap_two_sample_diff_ci: empty sample")

    point_a = float(metric_fn(y_true_a_arr, y_pred_a_arr))
    point_b = float(metric_fn(y_true_b_arr, y_pred_b_arr))
    point_diff = point_a - point_b

    rng = np.random.default_rng(seed)
    diffs = np.empty(n_resamples)
    for i in range(n_resamples):
        idx_a = rng.integers(0, n_a, n_a)
        idx_b = rng.integers(0, n_b, n_b)
        diffs[i] = metric_fn(y_true_a_arr[idx_a], y_pred_a_arr[idx_a]) - metric_fn(
            y_true_b_arr[idx_b], y_pred_b_arr[idx_b]
        )

    alpha = (1 - confidence) / 2
    lower, upper = np.quantile(diffs, [alpha, 1 - alpha])
    significant = not (lower <= 0 <= upper)
    return {
        "point_a": round(point_a, 4),
        "point_b": round(point_b, 4),
        "point_diff": round(point_diff, 4),
        "ci_lower": round(float(lower), 4),
        "ci_upper": round(float(upper), 4),
        "confidence": confidence,
        "n_a": n_a,
        "n_b": n_b,
        "n_resamples": n_resamples,
        "significant_at_confidence": significant,
        "method": (
            "percentile bootstrap on the difference between two independently-resampled "
            "samples (not a paired/McNemar comparison -- a and b are different alerts)"
        ),
        "interpretation": (
            f"metric(a)-metric(b) = {point_diff:+.4f}, {int(confidence * 100)}% CI "
            f"[{lower:+.4f}, {upper:+.4f}]. "
            + (
                "This excludes 0, so the gap is a real effect at this sample size, not "
                "sampling noise."
                if significant
                else "This includes 0, so the gap is not distinguishable from sampling "
                "noise at this sample size."
            )
        ),
    }


def wilcoxon_signed_rank(deltas: list, confidence: float = 0.95) -> dict:
    """Two-sided Wilcoxon signed-rank test on a set of paired deltas vs. 0.

    Used where bootstrap_metric_ci doesn't apply: a handful of per-seed
    deltas (e.g. 5 row-split-minus-group-split accuracies, one per
    GroupShuffleSplit seed) rather than a large per-row sample. Non-
    parametric on purpose -- n is small enough (5 seeds) that a normality
    assumption isn't defensible.
    """
    deltas_arr = np.asarray(deltas, dtype=float)
    n = len(deltas_arr)
    if n == 0:
        raise ValueError("wilcoxon_signed_rank: empty sample")
    if np.all(deltas_arr == 0):
        # scipy.stats.wilcoxon raises on an all-zero input rather than
        # returning a (correct) p=1.0 -- handle it explicitly instead of
        # letting the caller's run crash on a degenerate-but-valid result.
        return {
            "statistic": 0.0,
            "p_value": 1.0,
            "n": n,
            "median": 0.0,
            "method": "wilcoxon signed-rank, two-sided, vs. median 0 (all deltas were exactly 0)",
        }
    statistic, p_value = scipy_stats.wilcoxon(deltas_arr, alternative="two-sided")
    return {
        "statistic": round(float(statistic), 4),
        "p_value": float(p_value),
        "n": n,
        "median": round(float(np.median(deltas_arr)), 4),
        "method": "wilcoxon signed-rank, two-sided, vs. median 0",
    }


def pearson_correlation(x: list, y: list) -> dict:
    """Pearson r and its two-sided p-value between two equal-length series.

    Used for the overlap-vs-inflation scatter (M2.1 PART C): x = incident
    overlap percentage, y = accuracy delta vs. the clean held-out baseline,
    across a handful of evaluation sets. n this small means the p-value is
    weak evidence on its own -- report alongside r, not instead of it.
    """
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    n = len(x_arr)
    if n != len(y_arr):
        raise ValueError("pearson_correlation: x and y must be the same length")
    if n < 2:
        raise ValueError("pearson_correlation: need at least 2 points")
    r, p_value = scipy_stats.pearsonr(x_arr, y_arr)
    return {
        "r": round(float(r), 4),
        "p_value": float(p_value),
        "n": n,
        "method": "pearson product-moment correlation, two-sided p-value",
    }


def cochrans_q(correct_matrix: np.ndarray) -> dict:
    """Cochran's Q: omnibus test that >=2 classifiers have equal accuracy.

    `correct_matrix` is (n_items, k_classifiers) of 0/1 (wrong/right), same
    items scored by every classifier. McNemar only compares a pair; this is
    the classifier-suite-wide equivalent asked for across M1-M6 in M2.4.
    Not in scipy (scipy has no Cochran's Q) and statsmodels is not a
    dependency of this project for one formula, so it's the direct textbook
    computation: Q = k(k-1) * sum_j(Cj - Cbar)^2 / (k*sum_i(Ri) - sum_i(Ri^2)),
    df = k-1, p-value from the chi-squared survival function.
    """
    matrix = np.asarray(correct_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("cochrans_q: correct_matrix must be 2D (n_items, k_classifiers)")
    n, k = matrix.shape
    if n == 0 or k < 2:
        raise ValueError("cochrans_q: need >=1 item and >=2 classifiers")

    column_totals = matrix.sum(axis=0)  # Cj: correct count per classifier
    row_totals = matrix.sum(axis=1)  # Ri: correct count per item
    column_mean = column_totals.mean()
    denominator = k * row_totals.sum() - float((row_totals**2).sum())
    if denominator == 0:
        # every item scored identically (all correct or all wrong) by every
        # classifier -- Q is undefined, not zero; say so rather than divide
        # by zero or report a misleading p=1.0.
        return {
            "Q": None,
            "df": k - 1,
            "p_value": None,
            "k": k,
            "n": n,
            "method": "cochran's Q, undefined: no variation in per-item outcomes across classifiers",
        }

    q_statistic = k * (k - 1) * float(((column_totals - column_mean) ** 2).sum()) / denominator
    df = k - 1
    p_value = float(scipy_stats.chi2.sf(q_statistic, df))
    return {
        "Q": round(q_statistic, 4),
        "df": df,
        "p_value": p_value,
        "k": k,
        "n": n,
        "method": "cochran's Q, chi-squared approximation, omnibus test across k classifiers' per-item correctness",
    }
