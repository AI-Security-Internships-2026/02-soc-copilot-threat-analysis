"""
M2.1 PART C follow-up -- why incident-overlap rate does not correlate with
accuracy inflation across our evaluation sets.

Issue #31. The original scatter reported Pearson r=0.1139, p=0.8861 against an
expected r>=0.90, and the issue's instruction is explicit: report the number of
observations, explain the null, compare the 209-alert control against the other
samples for difficulty and composition differences, and **do not tune the
experiment to reach r>=0.90**. Nothing here is tuned; the null stands.

Two findings, in order of importance.

1. THE CORRELATION IS UNIDENTIFIED, NOT MERELY WEAK. n is 4 -- four evaluation
   *sets*, not four alerts -- across only three distinct x-values, two of them
   tied at 0% overlap. Leave-one-out shows the estimate has no stability at all:
   dropping one point gives r=+0.99, dropping a different one gives r=-0.996.
   A statistic that swings the full width of its range on one observation is not
   evidence of anything, in either direction.

2. THE POINTS DIFFER ON MORE THAN OVERLAP. control_209 is not an independent
   sample: it is the evidence-rich subset of train_sampled_999, selected by
   should_use_fallback()==False. It therefore shares its parent's leakage
   regime while differing from it on two axes that have nothing to do with
   overlap -- class balance and intrinsic difficulty. Those differences are
   larger than the effect the scatter was built to detect.

This does not weaken Section 4.12. The causal test there holds composition fixed
by class-balancing both buckets to identical per-class counts, which is what
isolates the leakage effect (+0.2433). A four-point observational scatter across
sets that differ in construction was never the instrument for that question.

Run:  venv/bin/python experiments/m2_1_overlap_correlation_analysis.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.fallback_classifier import _load_model, _to_feature_frame, should_use_fallback
from src.data.schema import TARGET_COLUMN
from src.models.decision import resolve_label

SCATTER = Path("experiments/results/m2_1_historical_eval_overlap.json")
OUT = Path("experiments/results/m2_1_overlap_correlation_analysis.json")
CACHE = Path("experiments/results/evaluation_samples")


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def profile(df: pd.DataFrame, model, encoders) -> dict:
    """Difficulty and composition of an evaluation set, independent of overlap."""
    margins, correct, classes = [], [], []
    for _, row in df.iterrows():
        alert = row.to_dict()
        truth = alert.pop(TARGET_COLUMN)
        proba = model.predict_proba(_to_feature_frame(alert, model, encoders))[0]
        ordered = np.sort(proba)[::-1]
        margins.append(float(ordered[0] - ordered[1]))
        correct.append(bool(resolve_label(model.classes_, proba) == truth))
        classes.append(truth)
    balance = pd.Series(classes).value_counts(normalize=True).round(4).to_dict()
    return {
        "n": int(len(df)),
        "accuracy": round(float(np.mean(correct)), 4),
        "rf_margin_mean": round(float(np.mean(margins)), 4),
        "rf_margin_median": round(float(np.median(margins)), 4),
        "class_balance": balance,
        "majority_class_floor": round(float(max(balance.values())), 4),
    }


def main() -> None:
    scatter = json.loads(SCATTER.read_text())
    pts = scatter["points"]
    x = [p["incident_level_overlap_pct"] for p in pts]
    y = [p["delta_vs_0_6998"] for p in pts]

    r, p = pearsonr(x, y)
    rho, sp = spearmanr(x, y)

    loo = []
    for i, pt in enumerate(pts):
        xs = [v for j, v in enumerate(x) if j != i]
        ys = [v for j, v in enumerate(y) if j != i]
        rr, pp = pearsonr(xs, ys)
        loo.append({"dropped": pt["name"], "r": round(float(rr), 4),
                    "p_value": round(float(pp), 4)})

    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    parent = pd.read_csv(CACHE / "guide_balanced_333_per_class_seed_42.csv", low_memory=False)
    held = pd.read_csv(CACHE / "guide_test_balanced_333_per_class_seed_42.csv", low_memory=False)
    mask = parent.apply(
        lambda r_: not should_use_fallback(r_.drop(TARGET_COLUMN).to_dict()), axis=1)

    profiles = {
        "train_sampled_999": profile(parent, model, encoders),
        "control_209": profile(parent[mask], model, encoders),
        "held_out_999": profile(held, model, encoders),
    }

    sub, par = profiles["control_209"], profiles["train_sampled_999"]
    result = {
        "experiment": "M2.1 PART C follow-up -- why overlap rate does not "
                      "correlate with inflation (issue #31)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "n_observations": len(pts),
        "n_observations_note": "four evaluation SETS, not four alerts. This is the "
                               "number the correlation is computed over.",
        "distinct_x_values": sorted(set(x)),
        "n_tied_at_zero_overlap": sum(1 for v in x if v == 0),
        "pearson": {"r": round(float(r), 4), "p_value": round(float(p), 4), "n": len(pts)},
        "spearman": {"rho": round(float(rho), 4), "p_value": round(float(sp), 4)},
        "leave_one_out": loo,
        "leave_one_out_interpretation":
            "Dropping control_209 gives r=+0.99; dropping train_sampled_999 gives "
            "r=-0.996. The estimate swings the full width of its range on one "
            "observation, so it is unidentified rather than weak. No conclusion "
            "about the sign of the relationship is supportable from these points.",
        "set_profiles": profiles,
        "control_209_is_a_subset_of_train_sampled_999": True,
        "composition_confounds": {
            "class_balance": "control_209 is "
                             f"{sub['class_balance']}, against an exactly balanced "
                             f"{par['class_balance']} for every other set. The "
                             "evidence-density filter selects non-uniformly across "
                             "classes, so its majority-class floor is "
                             f"{sub['majority_class_floor']} rather than "
                             f"{par['majority_class_floor']} -- a different baseline, "
                             "not a different amount of leakage.",
            "intrinsic_difficulty": "control_209's mean RF decision margin is "
                                    f"{sub['rf_margin_mean']} against {par['rf_margin_mean']} "
                                    "for its own parent set, a gap of "
                                    f"{round(sub['rf_margin_mean'] - par['rf_margin_mean'], 4)}. "
                                    "The evidence-rich filter selects alerts the "
                                    "classifier is less certain about.",
            "net_effect": "Within one leakage regime -- same parent sample -- the "
                          f"evidence-rich subset scores {round(sub['accuracy'] - par['accuracy'], 4)} "
                          "accuracy. That swamps the effect the scatter was built to "
                          "detect, in the opposite direction.",
        },
        "conclusion":
            "Overlap rate alone does not explain inflation magnitude across these "
            "evaluation sets, and this analysis does not attempt to make it. The "
            "four sets differ in construction as well as in overlap, and with n=4 "
            "over three distinct x-values the correlation is unidentified. The "
            "leakage effect is established instead by the controlled comparison in "
            "Section 4.12, which holds class composition fixed and yields +0.2433 "
            "with a 95% CI excluding zero.",
        "expected_min_r_not_met_and_not_pursued": {
            "expected": scatter.get("expected_min_r"),
            "observed": round(float(r), 4),
            "note": "Per issue #31, no attempt was made to tune the experiment "
                    "toward the expected value. The null is reported as measured.",
        },
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    print(f"n observations (evaluation sets): {len(pts)}")
    print(f"distinct x-values: {sorted(set(x))} ({sum(1 for v in x if v == 0)} tied at 0)")
    print(f"Pearson r={r:.4f} p={p:.4f} | Spearman rho={rho:.4f} p={sp:.4f}\n")
    print("leave-one-out:")
    for e in loo:
        print(f"  drop {e['dropped']:20} r={e['r']:+.4f} p={e['p_value']:.4f}")
    print("\nset profiles:")
    print(f"  {'set':20} {'n':>6} {'acc':>7} {'margin':>8} {'floor':>7}  balance")
    for k, v in profiles.items():
        print(f"  {k:20} {v['n']:>6} {v['accuracy']:>7.4f} {v['rf_margin_mean']:>8.4f} "
              f"{v['majority_class_floor']:>7.4f}  {v['class_balance']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
