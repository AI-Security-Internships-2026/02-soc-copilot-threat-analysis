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

from __future__ import annotations

import numpy as np


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
