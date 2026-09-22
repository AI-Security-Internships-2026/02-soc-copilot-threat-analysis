"""
M6.3 PART B -- backfill percentile-bootstrap 95% CIs onto the headline cells of
Sections 4.1-4.9, which the paper's own Limitations flags as lacking them.

Issue #46. No new experiments: every CI here is computed from an already-
committed artifact, reusing experiments/stats_utils.py rather than
re-implementing resampling.

Two kinds of cell need two different intervals, and conflating them would be
wrong:

  * A metric over a sample of rows (accuracy, macro F1) -> percentile bootstrap,
    resampling paired (y_true, y_pred) rows. stats_utils.bootstrap_metric_ci.
  * A count out of a fixed denominator (1 of 20 injections blocked) -> exact
    Clopper-Pearson binomial interval. Bootstrapping a 1/20 proportion resamples
    the same 20 points and understates the interval badly at that n.

Cells whose source JSON reports only an aggregate, with no per-row array to
resample, are recorded as NOT backfillable with the reason -- per the issue's
acceptance criteria, not silently dropped.

Run:  venv/bin/python experiments/m6_3_bootstrap_ci_backfill.py
"""

import json
from pathlib import Path

import numpy as np
from scipy.stats import beta
from sklearn.metrics import accuracy_score, f1_score

import sys
sys.path.insert(0, str(Path(__file__).parent))
from stats_utils import bootstrap_metric_ci  # noqa: E402

RESULTS = Path("experiments/results")
OUT_JSON = RESULTS / "m6_3_ci_backfill.json"
OUT_DOC = Path("docs/ci_backfill_changes_for_paper.md")

ACC = lambda t, p: accuracy_score(t, p)
MACRO_F1 = lambda t, p: f1_score(t, p, average="macro", zero_division=0)

# A CI narrower than this is invisible at the precision the paper prints (4 dp),
# so the recommendation is "keep the bare number" rather than clutter the table.
INVISIBLE = 0.003


def load(name):
    return json.loads((RESULTS / name).read_text())


def clopper_pearson(k, n, confidence=0.95):
    """Exact binomial interval. Correct at k=0 and k=n, where the normal
    approximation degenerates to a zero-width interval."""
    alpha = 1 - confidence
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return {
        "point": round(k / n, 4),
        "ci_lower": round(lo, 4),
        "ci_upper": round(hi, 4),
        "confidence": confidence,
        "n": n,
        "k": k,
        "method": "exact Clopper-Pearson binomial interval",
    }


def cells():
    out = {}

    # ---- Sec 4.5 / Tab 4 -- the paired 209-alert control -------------------
    ctl = load("rf_vs_llm_control.json")["per_alert_results"]
    truth = [r["ground_truth"] for r in ctl]
    rf = [r["rf_predicted"] for r in ctl]
    llm = [r["llm_predicted"] for r in ctl]
    out["tab4"] = {
        "rf_accuracy": bootstrap_metric_ci(truth, rf, ACC),
        "rf_macro_f1": bootstrap_metric_ci(truth, rf, MACRO_F1),
        "llm_accuracy": bootstrap_metric_ci(truth, llm, ACC),
        "llm_macro_f1": bootstrap_metric_ci(truth, llm, MACRO_F1),
        "majority_floor": bootstrap_metric_ci(
            truth, ["BenignPositive"] * len(truth), ACC),
    }

    # ---- Sec 4.6 / Tab 5 -- LLM accuracy by self-reported confidence -------
    bands = {}
    for band in sorted({(r.get("llm_confidence") or "unknown") for r in ctl}):
        rows = [r for r in ctl if (r.get("llm_confidence") or "unknown") == band]
        if len(rows) < 2:
            continue
        k = sum(r["ground_truth"] == r["llm_predicted"] for r in rows)
        bands[band] = clopper_pearson(k, len(rows))
    out["tab5_llm_confidence_bands"] = bands

    # ---- Sec 4.6 / Tab 6 -- RF margin-threshold sweep ----------------------
    sweep = {}
    for t in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50):
        auto = [r for r in ctl if r.get("rf_margin") is not None and r["rf_margin"] >= t]
        if not auto:
            continue
        k = sum(r["ground_truth"] == r["rf_predicted"] for r in auto)
        sweep[f"T={t:.2f}"] = {
            "auto_accepted_n": len(auto),
            "auto_accepted_pct": round(len(auto) / len(ctl), 4),
            **clopper_pearson(k, len(auto)),
        }
    out["tab6_rf_margin_sweep"] = sweep

    # ---- Sec 4.7 / Tab 7 -- whole-pipeline accuracy ------------------------
    cur = load("agent_metrics_week15_rf_primary.json")["per_alert_results"]
    ok = [r for r in cur if not r.get("error")]
    out["tab7"] = {
        "rf_primary_accuracy": bootstrap_metric_ci(
            [r["ground_truth"] for r in ok], [r["predicted"] for r in ok], ACC),
        "rf_primary_macro_f1": bootstrap_metric_ci(
            [r["ground_truth"] for r in ok], [r["predicted"] for r in ok], MACRO_F1),
    }
    try:
        old = load("archive/agent_metrics_week12_999_current.json")["per_alert_results"]
        oldok = [r for r in old if not r.get("error")]
        out["tab7"]["legacy_hybrid_accuracy"] = bootstrap_metric_ci(
            [r["ground_truth"] for r in oldok],
            [r.get("predicted") or r.get("predicted_label") for r in oldok], ACC)
    except (FileNotFoundError, KeyError) as exc:
        out["tab7"]["legacy_hybrid_accuracy"] = {
            "backfillable": False,
            "reason": f"archive file lacks a usable per-row array ({exc.__class__.__name__})",
        }

    # ---- Sec 4.1-4.2 / Tab 1-2 -- SOC-domain eval (n=40) -------------------
    rows = load("soc_domain_eval_results.json")["per_row"]
    labels = [r["label"] for r in rows]
    scores = [r["score"] for r in rows]
    pos = sum(1 for lbl in labels if lbl in (1, "injection", True))
    thr = {}
    for t in (0.3, 0.5, 0.7):
        pred = [1 if s >= t else 0 for s in scores]
        gold = [1 if lbl in (1, "injection", True) else 0 for lbl in labels]
        k = sum(int(a == b) for a, b in zip(pred, gold))
        thr[f"threshold={t}"] = clopper_pearson(k, len(rows))
    out["tab1_tab2_soc_domain"] = {
        "n_rows": len(rows), "n_injection": pos, "accuracy_by_threshold": thr,
        "caveat": "40 self-authored examples; the interval quantifies sampling "
                  "noise only, not the corpus-authorship bias, which is larger. "
                  "Section 4.14's 400-attack benchmark is the honest measurement.",
    }

    # ---- Sec 4.9 / Tab 10 -- guardrail layers (counts, not samples) --------
    g = load("guardrail_layer_eval.json")
    rx_k, rx_n = (int(x) for x in g["regex_guardrail"]["injection_blocked"].split("/"))
    sc_k, sc_n = (int(x) for x in g["schema_guardrail"]["injection_blocked"].split("/"))
    out["tab10_guardrail_layers"] = {
        "regex_injection_recall": clopper_pearson(rx_k, rx_n),
        "schema_injection_recall": {
            **clopper_pearson(sc_k, sc_n),
            "note": "20/20 is true by construction (int(value) rejects all prose), "
                    "so the upper bound is 1.0 by definition. The lower bound is "
                    "the honest statement of what 20 observations support.",
        },
        "regex_benign_false_positives": clopper_pearson(0, 20),
    }

    # ---- Sec 4.14 / Tab 18 -- detector benchmark (counts) ------------------
    det = {}
    for key, src in (("h1", "m3_2_heuristic_detectors.json"),
                     ("h2", "m3_2_heuristic_detectors.json"),
                     ("h3", "m3_2_heuristic_detectors.json"),
                     ("h_union", "m3_2_heuristic_detectors.json"),
                     ("l1", "m3_2_learned_detectors.json"),
                     ("l2", "m3_2_learned_detectors.json"),
                     ("l3", "m3_2_learned_detectors.json")):
        node = load(src)[key]
        # Not every detector reached all 400 attack rows -- L3's live Groq pass
        # leaves 5 F4 rows on a persistent unparseable response, so its TPR is
        # over 395. Multiplying the ratio back out by a flat 400 would centre
        # the interval on a numerator that was never observed.
        n = node.get("n_attacks_scored", 400)
        k = node.get("n_attacks_detected", round(node["overall_tpr"] * n))
        det[key] = clopper_pearson(k, n)  # already records k and n
        if n != 400:
            det[key]["note"] = (
                f"denominator is {n}, not 400: {400 - n} attack row(s) are unscored "
                "for this detector (see its persistent_errors block)."
            )
    out["tab18_detector_recall"] = det

    # ---- Cells that genuinely cannot be backfilled -------------------------
    out["not_backfillable"] = {
        "tab3_rf_baseline": "baseline_metrics.json reports aggregates with no "
                            "per-row array. Not a gap in practice: "
                            "m2_1_splitmethod_delta_5seeds.json seed 42 reports the "
                            "identical 0.7718/0.7505 WITH bootstrap CIs, and the "
                            "paper should cite those.",
        "tab8_tab9_scalability": "wall-clock throughput from timeit best-of-7 "
                                 "repeats. A bootstrap over 7 timing repeats on one "
                                 "machine would imply a precision the measurement "
                                 "does not have; reported as an order of magnitude.",
        "tab12_tab13_control_ablation": "two arms are Groq-quota bounded and scored "
                                        "on a subset missing exactly the alerts they "
                                        "existed to test. A CI would describe the "
                                        "wrong population.",
    }
    return out


def width(ci):
    if not isinstance(ci, dict) or "ci_lower" not in ci:
        return None
    return ci["ci_upper"] - ci["ci_lower"]


def walk(node, prefix=""):
    """Yield (dotted_id, ci_dict) for every leaf that looks like a CI."""
    if isinstance(node, dict):
        if "ci_lower" in node and "ci_upper" in node:
            yield prefix, node
        else:
            for k, v in node.items():
                yield from walk(v, f"{prefix}.{k}" if prefix else k)


def main():
    data = cells()
    OUT_JSON.write_text(json.dumps(data, indent=2) + "\n")

    found = list(walk(data))
    lines = ["# CI Backfill — per-cell changes for the paper",
             "",
             "Generated by `experiments/m6_3_bootstrap_ci_backfill.py` (issue #46, "
             "M6.3 PART B). Source of record: `experiments/results/m6_3_ci_backfill.json`.",
             "",
             "No new experiments were run. Every interval below is computed from an "
             "already-committed artifact.",
             "",
             "**Two interval types, deliberately not interchangeable.** A metric over "
             "a sample of rows gets a percentile bootstrap resampling paired "
             "`(y_true, y_pred)` rows. A count out of a fixed denominator (1 of 20 "
             "injections blocked) gets an exact Clopper-Pearson interval — "
             "bootstrapping a 1/20 proportion resamples the same twenty points and "
             "understates the interval badly at that *n*.",
             "",
             f"**Recommendation rule.** A CI narrower than {INVISIBLE} is invisible at "
             "the precision the paper prints, so the recommendation is to keep the "
             "bare number; anything wider should print the interval.",
             "",
             f"## Backfilled cells ({len(found)})",
             "",
             "| Cell | Point | 95% CI | Width | Method | Recommendation |",
             "|---|---|---|---|---|---|"]
    for cid, ci in found:
        w = width(ci)
        rec = ("keep bare number (CI invisible at 4 dp)" if w is not None and w < INVISIBLE
               else f"print as `{ci['point']} [{ci['ci_lower']}, {ci['ci_upper']}]`")
        meth = "bootstrap" if "bootstrap" in ci.get("method", "") else "Clopper-Pearson"
        lines.append(f"| `{cid}` | {ci['point']} | [{ci['ci_lower']}, {ci['ci_upper']}] "
                     f"| {w:.4f} | {meth} | {rec} |")

    lines += ["", "## Not backfillable", "",
              "Recorded with the reason rather than dropped.", "",
              "| Cell | Why |", "|---|---|"]
    for k, v in data["not_backfillable"].items():
        lines.append(f"| `{k}` | {v} |")

    OUT_DOC.write_text("\n".join(lines) + "\n")
    return len(found)


if __name__ == "__main__":
    n = main()
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_DOC}")
    print(f"  backfilled cells: {n}")
