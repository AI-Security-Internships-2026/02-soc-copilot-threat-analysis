"""
M5.1 PART A -- the three ablation configurations the paper is missing.

Issue #42. Sections 4.7 and 4.11 already establish two of the five configs
(full A4, and full-minus-LLM-explanation); re-running those would cost LLM
budget to reproduce a known result. This covers the remaining three:

  nomitre        fetch_mitre_context stubbed out -- the ATT&CK enrichment never
                 reaches the explanation prompt
  noguardrails   regex and schema stages removed -- alerts reach the classifier
                 unfiltered
  nohitl         review threshold T=0 -- every verdict auto-accepted

**What this expects to find, and why that is the interesting part.**
`classify_with_rf` reads `state["raw_alert"]` directly. It does not read the
built context block, and it does not read `mitre_context`. If the architecture
is what Section 4.7 claims, none of these three ablations can move a single
verdict -- so the honest test is not "accuracy within +/-0.005" but *exact
element-wise label identity*, which is strictly stronger and fails loudly if
the claim is wrong. That is what this measures.

The ablation graphs are built here rather than by extending
`src/agent/graph.py`, so an ablation-only concern cannot reach production
wiring.

Explanation quality uses two automated proxies, D1 and D2. They are proxies,
not human judgement: issue #40 PART A is the human study that would validate
them, and it has not run. Read them as a signal about whether the enrichment
reaches the text at all, not as a quality score.

Run:  venv/bin/python experiments/m5_1_ablation_3missing.py
      venv/bin/python experiments/m5_1_ablation_3missing.py --sample-size 999
      venv/bin/python experiments/m5_1_ablation_3missing.py --skip-explanation-study
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from langgraph.graph import StateGraph, START, END
from sklearn.metrics import accuracy_score, f1_score, recall_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.state import AlertState
from src.agent import nodes as N
from src.agent.guardrails import inspect_alert
from src.agent.schema_guardrail import validate_field_types
from src.data.schema import TARGET_COLUMN
from experiments.stats_utils import bootstrap_metric_ci

OUT_JSON = Path("experiments/results/m5_1_ablation_5config.json")
OUT_CSV = Path("experiments/results/m5_1_ablation_5config.csv")
CACHE = Path("experiments/results/evaluation_samples")
BENCHMARK = Path("datasets/soc_injection_benchmark_v1.csv")

ACC = lambda t, p: accuracy_score(t, p)
MACRO_F1 = lambda t, p: f1_score(t, p, average="macro", zero_division=0)


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------
# ablation graph variants
# --------------------------------------------------------------------------

def _stub_mitre(state: AlertState) -> AlertState:
    """The nomitre arm: the node still runs, so the graph shape is unchanged,
    but it contributes no enrichment. Removing the node entirely would also
    change the node count, confounding the latency column."""
    state["mitre_context"] = ""
    return state


def build_ablation_graph(config: str, threshold: float):
    """rf_primary, with one stage disabled. Routing predicates are closed over
    `threshold` so the nohitl arm does not mutate module state."""
    graph = StateGraph(AlertState)

    def route_gate(state: AlertState) -> str:
        if state.get("error") or not state.get("predicted_label"):
            return "human_review"
        margin = state.get("rf_margin")
        if margin is None or margin < threshold:
            return "human_review"
        return "end"

    graph.add_node("fetch_mitre_context",
                   _stub_mitre if config == "nomitre" else N.fetch_mitre_context)
    graph.add_node("build_context", N.build_context)
    graph.add_node("classify_with_rf", N.classify_with_rf)
    graph.add_node("explain_with_llm", N.explain_with_llm)
    graph.add_node("human_review", N.human_review_node)

    if config == "noguardrails":
        graph.add_edge(START, "fetch_mitre_context")
    else:
        graph.add_node("regex_guardrail", N.apply_regex_guardrail)
        graph.add_node("schema_guardrail", N.apply_schema_guardrail)
        graph.add_edge(START, "regex_guardrail")
        graph.add_conditional_edges(
            "regex_guardrail", N.route_after_guardrail,
            {"continue": "schema_guardrail", "human_review": "human_review"})
        graph.add_conditional_edges(
            "schema_guardrail", N.route_after_schema_guardrail,
            {"continue": "fetch_mitre_context", "human_review": "human_review"})

    graph.add_edge("fetch_mitre_context", "build_context")
    graph.add_edge("build_context", "classify_with_rf")
    graph.add_edge("classify_with_rf", "explain_with_llm")
    graph.add_conditional_edges("explain_with_llm", route_gate,
                                {"end": END, "human_review": "human_review"})
    graph.add_edge("human_review", END)
    return graph.compile()


CONFIGS = {
    "full":         dict(config="full",         threshold=N.RF_REVIEW_MARGIN_THRESHOLD),
    "nomitre":      dict(config="nomitre",      threshold=N.RF_REVIEW_MARGIN_THRESHOLD),
    "noguardrails": dict(config="noguardrails", threshold=N.RF_REVIEW_MARGIN_THRESHOLD),
    "nohitl":       dict(config="nohitl",       threshold=0.0),
}


# --------------------------------------------------------------------------
# classification arm
# --------------------------------------------------------------------------

def score_config(name: str, sample: pd.DataFrame) -> dict:
    graph = build_ablation_graph(**CONFIGS[name])
    truths, preds, latencies, auto = [], [], [], 0
    errors = 0

    for _, row in sample.iterrows():
        alert = row.to_dict()
        truth = alert.pop(TARGET_COLUMN)
        t0 = time.perf_counter()
        state = graph.invoke({"raw_alert": alert})
        latencies.append((time.perf_counter() - t0) * 1000)
        label = state.get("predicted_label")
        if state.get("error"):
            errors += 1
        truths.append(truth)
        preds.append(label)
        if not state.get("needs_human_review"):
            auto += 1

    scored = [(t, p) for t, p in zip(truths, preds) if p is not None]
    st, sp = [t for t, _ in scored], [p for _, p in scored]
    ci = bootstrap_metric_ci(st, sp, ACC, n_resamples=2000) if scored else None

    return {
        "config": name,
        "n": len(sample),
        "n_scored": len(scored),
        "n_errors": errors,
        "accuracy": round(accuracy_score(st, sp), 4) if scored else None,
        "accuracy_ci": [ci["ci_lower"], ci["ci_upper"]] if ci else None,
        "macro_f1": round(f1_score(st, sp, average="macro", zero_division=0), 4) if scored else None,
        "true_positive_recall": round(
            recall_score(st, sp, labels=["TruePositive"], average="macro",
                         zero_division=0), 4) if scored else None,
        "auto_accept_pct": round(auto / len(sample), 4),
        "latency_p50_ms": round(float(np.percentile(latencies, 50)), 3),
        "latency_p95_ms": round(float(np.percentile(latencies, 95)), 3),
        "_labels": preds,
    }


# --------------------------------------------------------------------------
# guardrail arm -- only meaningful for noguardrails
# --------------------------------------------------------------------------

def guardrail_tpr(with_guardrails: bool) -> dict:
    """Fraction of the 400 benchmark attacks stopped before the classifier.

    Reuses M3.2's own loader and alert builder rather than reconstructing them,
    so this number is directly comparable to the published H1/H2 recalls: the
    payload lands in the field the benchmark names, not always AlertTitle.
    """
    from experiments.m3_2_heuristic_detectors import load_benchmark, _build_alert

    attacks = [r for r in load_benchmark() if r["_is_attack"]]
    if not with_guardrails:
        return {"n_attacks": len(attacks), "blocked": 0, "tpr": 0.0,
                "note": "guardrail stages removed; nothing inspects the payload, "
                        "so every attack reaches the classifier by construction"}
    blocked = 0
    for row in attacks:
        alert = _build_alert(row)
        if inspect_alert(alert) or validate_field_types(alert):
            blocked += 1
    return {"n_attacks": len(attacks), "blocked": blocked,
            "tpr": round(blocked / len(attacks), 4),
            "note": "H1 regex union H2 schema, via M3.2's own alert builder"}


# --------------------------------------------------------------------------
# explanation arm -- automated proxies, live LLM
# --------------------------------------------------------------------------

MITRE_ID = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")


def d1_grounded(text: str, alert: dict) -> bool:
    """D1: does the explanation cite a concrete value from THIS alert?

    Follows the Week 14 groundedness content analysis (see the comment above
    the system prompt in src/agent/nodes.py): text that references specific
    alert evidence rather than generic boilerplate.
    """
    if not text:
        return False
    low = text.lower()
    for field in ("SuspicionLevel", "LastVerdict", "Category"):
        v = str(alert.get(field, "")).strip()
        if v and v.lower() in low:
            return True
    if MITRE_ID.search(text) and MITRE_ID.search(str(alert.get("MitreTechniques", ""))):
        return True
    for field in ("AlertTitle", "DetectorId"):
        v = str(alert.get(field, "")).strip()
        if v and v.isdigit() and v in text:
            return True
    return False


def d2_mitre_match(text: str, alert: dict) -> bool | None:
    """D2: does the explanation name an ATT&CK technique the alert carries?
    None when the alert carries none -- excluded from the rate rather than
    counted as a failure."""
    raw = str(alert.get("MitreTechniques", "") or "")
    ids = set(MITRE_ID.findall(raw))
    if not ids:
        return None
    return bool(ids & set(MITRE_ID.findall(text or "")))


def explanation_study(sample: pd.DataFrame, n: int) -> dict:
    """Full vs nomitre on the same alerts, with the LLM actually called."""
    was = os.environ.pop("SOC_COPILOT_SKIP_EXPLANATION", None)
    subset = sample.head(n)
    out = {}
    try:
        for name in ("full", "nomitre"):
            graph = build_ablation_graph(**CONFIGS[name])
            d1_hits, d2_hits, d2_eligible, generated = 0, 0, 0, 0
            for _, row in subset.iterrows():
                alert = row.to_dict()
                alert.pop(TARGET_COLUMN, None)
                state = graph.invoke({"raw_alert": alert})
                text = state.get("rationale") or ""
                if state.get("rationale_status") != "generated":
                    continue
                generated += 1
                if d1_grounded(text, alert):
                    d1_hits += 1
                m = d2_mitre_match(text, alert)
                if m is not None:
                    d2_eligible += 1
                    d2_hits += int(m)
            out[name] = {
                "n_requested": len(subset),
                "n_explanations_generated": generated,
                "d1_grounded_rate": round(d1_hits / generated, 4) if generated else None,
                "d2_mitre_match_rate": round(d2_hits / d2_eligible, 4) if d2_eligible else None,
                "d2_eligible": d2_eligible,
            }
    finally:
        if was is not None:
            os.environ["SOC_COPILOT_SKIP_EXPLANATION"] = was
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-size", type=int, default=15000)
    ap.add_argument("--explanation-n", type=int, default=100)
    ap.add_argument("--skip-explanation-study", action="store_true")
    args = ap.parse_args()

    per_class = args.sample_size // 3
    path = CACHE / f"guide_test_balanced_{per_class}_per_class_seed_42.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found; generate it with guide_test_holdout_eval.py")
    sample = pd.read_csv(path, low_memory=False)

    # Classification runs offline. The explanation node still executes; it just
    # does not call out, which is exactly what Section 4.7's invariance claim
    # says is safe to do.
    os.environ["SOC_COPILOT_SKIP_EXPLANATION"] = "1"

    results = {}
    for name in CONFIGS:
        print(f"scoring config '{name}' over {len(sample)} held-out alerts...")
        results[name] = score_config(name, sample)
        r = results[name]
        print(f"    acc={r['accuracy']} macroF1={r['macro_f1']} "
              f"auto={r['auto_accept_pct']:.1%} p50={r['latency_p50_ms']}ms "
              f"errors={r['n_errors']}")

    base = results["full"]["_labels"]
    identity = {}
    for name, r in results.items():
        diffs = [i for i, (a, b) in enumerate(zip(base, r["_labels"])) if a != b]
        identity[name] = {
            "labels_identical_to_full": len(diffs) == 0,
            "n_label_differences": len(diffs),
            "first_differing_indices": diffs[:5],
        }
        r["delta_acc_vs_full"] = (round(r["accuracy"] - results["full"]["accuracy"], 6)
                                  if r["accuracy"] is not None else None)

    print("\nguardrail TPR on the 400-attack benchmark:")
    g_with = guardrail_tpr(True)
    g_without = guardrail_tpr(False)
    print(f"    with guardrails   : {g_with['blocked']}/{g_with['n_attacks']} = {g_with['tpr']:.4f}")
    print(f"    without (ablated) : {g_without['blocked']}/{g_without['n_attacks']} = {g_without['tpr']:.4f}")

    expl = None
    if not args.skip_explanation_study:
        print(f"\nexplanation study, live LLM, n={args.explanation_n} per arm...")
        expl = explanation_study(sample, args.explanation_n)
        for k, v in expl.items():
            print(f"    {k:12} D1={v['d1_grounded_rate']} D2={v['d2_mitre_match_rate']} "
                  f"(generated {v['n_explanations_generated']}/{v['n_requested']})")

    for r in results.values():
        r.pop("_labels", None)

    payload = {
        "experiment": "M5.1 PART A -- nomitre / noguardrails / nohitl ablations",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "evaluation_set": str(path),
        "configs": results,
        "label_identity_vs_full": identity,
        "guardrail_tpr": {"full": g_with, "noguardrails": g_without},
        "explanation_study": expl,
        "explanation_proxy_caveat":
            "D1 and D2 are automated proxies, not human judgement. D1 asks "
            "whether the text cites a concrete value from this alert; D2 whether "
            "it names an ATT&CK technique the alert carries. The human study that "
            "would validate them is issue #40 PART A and has not run.",
        "configs_not_rerun": {
            "full_A4": "Section 4.7, accuracy 0.7347 on n=999 -- already published",
            "no_llm_explanation": "Section 4.11 arm (b), 0 verdict mismatches over "
                                  "999 alerts -- already published; re-running would "
                                  "spend LLM budget to reproduce a known result",
        },
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")

    rows = []
    for name, r in results.items():
        rows.append({
            "config": name,
            "acc": r["accuracy"],
            "acc_ci_low": r["accuracy_ci"][0] if r["accuracy_ci"] else None,
            "acc_ci_high": r["accuracy_ci"][1] if r["accuracy_ci"] else None,
            "macrof1": r["macro_f1"],
            "tprecall": r["true_positive_recall"],
            "d1_grounded": (expl or {}).get(name, {}).get("d1_grounded_rate"),
            "d2_mitrematch": (expl or {}).get(name, {}).get("d2_mitre_match_rate"),
            "guardrail_tpr_m3": g_without["tpr"] if name == "noguardrails" else g_with["tpr"],
            "latency_p50_ms": r["latency_p50_ms"],
            "auto_accept_pct": r["auto_accept_pct"],
            "delta_acc_vs_full_within_ci": r["delta_acc_vs_full"],
        })
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)

    print("\nlabel identity vs full:")
    for name, v in identity.items():
        print(f"    {name:12} identical={v['labels_identical_to_full']} "
              f"diffs={v['n_label_differences']}")
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
