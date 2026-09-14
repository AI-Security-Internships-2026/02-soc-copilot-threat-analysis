"""
M6.1 PART C backfill -- the effect sizes and multiplicity corrections the
compliance audit flags as missing.

Issue #44. Two gaps, both closable from committed counts with no new experiment:

  R2  McNemar p-values reported without an effect size. McNemar's OR is b/c on
      the discordant cells, and its CI follows from the exact binomial CI on
      b/(b+c) -- the concordant cells carry no information about the OR, which
      is exactly why the test is paired.

  R4  The M2.4 classifier family runs an omnibus Cochran's Q and then pairwise
      McNemar tests. The omnibus licenses the family but does not correct the
      pairwise p-values; Holm-Bonferroni does, and is uniformly more powerful
      than plain Bonferroni at the same family-wise error rate.

Run:  venv/bin/python experiments/m6_1_effect_sizes.py
"""

import json
from pathlib import Path

from scipy.stats import beta

RESULTS = Path("experiments/results")
OUT = RESULTS / "m6_1_effect_sizes.json"
ALPHA = 0.05


def load(name):
    return json.loads((RESULTS / name).read_text())


def mcnemar_odds_ratio(b, c, alpha=ALPHA):
    """OR = b/c with a CI derived from the exact (Clopper-Pearson) interval on
    p = b/(b+c). Under the null p = 0.5, i.e. OR = 1."""
    n = b + c
    if n == 0:
        return None
    point = float("inf") if c == 0 else b / c
    lo = 0.0 if b == 0 else beta.ppf(alpha / 2, b, n - b + 1)
    hi = 1.0 if b == n else beta.ppf(1 - alpha / 2, b + 1, n - b)
    to_or = lambda p: float("inf") if p >= 1 else p / (1 - p)
    return {
        "odds_ratio": round(point, 4) if point != float("inf") else None,
        "ci_lower": round(to_or(lo), 4),
        "ci_upper": round(to_or(hi), 4) if hi < 1 else None,
        "proportion_favouring_a": round(b / n, 4),
        "proportion_ci": [round(lo, 4), round(hi, 4)],
        "b_discordant_favouring_a": b,
        "c_discordant_favouring_b": c,
        "n_discordant": n,
        "method": "McNemar odds ratio b/c; CI from the exact Clopper-Pearson "
                  "interval on b/(b+c) mapped through p/(1-p). Null OR = 1.",
    }


def holm_bonferroni(pairs, alpha=ALPHA):
    """Holm step-down. Returns entries in ascending p order with the threshold
    each was compared against and whether it survives."""
    ordered = sorted(pairs.items(), key=lambda kv: kv[1])
    m = len(ordered)
    out, still_rejecting = [], True
    for i, (name, p) in enumerate(ordered):
        threshold = alpha / (m - i)
        if p > threshold:
            still_rejecting = False
        out.append({
            "comparison": name,
            "p_raw": p,
            "rank": i + 1,
            "holm_threshold": threshold,
            "significant_after_holm": bool(still_rejecting),
            # Holm-adjusted p, enforcing monotonicity
            "p_adjusted": min(1.0, max(
                (m - j) * q for j, (_, q) in enumerate(ordered[:i + 1]))),
        })
    return {
        "method": f"Holm-Bonferroni step-down, family-wise alpha = {alpha}, "
                  f"m = {m} pairwise tests",
        "family_size": m,
        "plain_bonferroni_threshold": alpha / m,
        "results": out,
    }


def main():
    out = {
        "experiment": "M6.1 PART C -- effect sizes and multiplicity corrections "
                      "for cells the compliance audit flagged",
        "alpha": ALPHA,
        "mcnemar_effect_sizes": {},
        "multiplicity": {},
    }

    # --- R2: the two McNemar tests reported without an effect size -------------
    c = load("rf_vs_llm_control.json")["paired_mcnemar_test"]
    out["mcnemar_effect_sizes"]["rf_vs_llm_209"] = {
        "source": "rf_vs_llm_control.json :: paired_mcnemar_test",
        "reports": "Tab 4 -- RF vs LLM on the identical 209 alerts",
        "p_value": c["p_value"],
        **mcnemar_odds_ratio(c["rf_correct_llm_wrong"], c["llm_correct_rf_wrong"]),
    }

    m = load("m2_4_m3a_vs_m7_mcnemar.json")
    out["mcnemar_effect_sizes"]["m3a_vs_m7_partial_241"] = {
        "source": "m2_4_m3a_vs_m7_mcnemar.json",
        "reports": "Sec 4.13 -- M3a vs M7, partial n=241",
        "superseded_by": m.get("superseded_by"),
        "p_value": m["p_value"],
        **mcnemar_odds_ratio(m["rf_correct_llm_wrong"], m["llm_correct_rf_wrong"]),
    }

    # --- R4: correct the M2.4 pairwise family ---------------------------------
    held = load("m2_4_heldout_n15k.json")
    pairs = held["mcnemar_pairs"]
    corrected = holm_bonferroni({k: v["p_value"] for k, v in pairs.items()})
    corrected["omnibus"] = {
        "test": "Cochran's Q across k=7 classifiers",
        "Q": held["cochrans_q_tabular_m1_m6"]["Q"],
        "df": held["cochrans_q_tabular_m1_m6"]["df"],
        "p_value": held["cochrans_q_tabular_m1_m6"]["p_value"],
        "note": "The omnibus rejects, which licenses the pairwise family. It does "
                "not correct the pairwise p-values -- Holm below does.",
    }
    corrected["odds_ratios_already_present"] = {
        k: v.get("odds_ratio_a_over_b") for k, v in pairs.items()
    }
    out["multiplicity"]["m2_4_classifier_pairwise"] = corrected

    # The 56-cell detector x family matrix reports recall rates, not hypothesis
    # tests. Stating that plainly is the honest close, not applying a correction
    # to quantities that carry no p-value.
    fam = load("m3_2_familywise_failure_analysis.json")
    out["multiplicity"]["m3_2_detector_family_matrix"] = {
        "cells": len(fam["detectors_included"]) * 7,
        "correction_applicable": False,
        "reason": "The 56 cells are per-family true-positive rates, not hypothesis "
                  "tests -- there is no p-value to correct. The matrix is reported "
                  "descriptively and no significance is claimed between cells.",
    }

    OUT.write_text(json.dumps(out, indent=2) + "\n")
    return out


if __name__ == "__main__":
    o = main()
    print(f"wrote {OUT}\n")
    for k, v in o["mcnemar_effect_sizes"].items():
        print(f"  {k}: OR={v['odds_ratio']} CI=[{v['ci_lower']}, {v['ci_upper']}] "
              f"on {v['n_discordant']} discordant")
    print()
    h = o["multiplicity"]["m2_4_classifier_pairwise"]
    print(f"  Holm-Bonferroni, m={h['family_size']}:")
    for r in h["results"]:
        print(f"    {r['comparison']:14} p={r['p_raw']:.4g} -> adj={r['p_adjusted']:.4g} "
              f"{'SIG' if r['significant_after_holm'] else 'ns'}")
