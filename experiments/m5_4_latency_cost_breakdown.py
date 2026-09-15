"""
M5.2 PART B -- per-stage latency, throughput and API cost.

Issue #43 (the file name follows the issue's own "old M5.4 content" label so the
two stay greppable together).

Operational question, not a research one: what does running this on a real SOC
queue cost, and where does the time actually go? The answer is dominated by one
stage, which is why the evidence-density router exists.

What is measured here and what is not:

  MEASURED LIVE   guardrail regex, schema check, RF inference, MITRE lookup,
                  HITL gate -- all offline, timed with perf_counter over many
                  repeats in this run.
  REUSED          LLM call latency, from the committed week-7 scalability
                  benchmark. Re-measuring would burn Groq quota to reproduce a
                  number already committed, and the routed path is dominated by
                  it either way.
  APPROXIMATED    token counts, via tiktoken. The deployed model is
                  openai/gpt-oss-20b on Groq, whose exact tokeniser is not
                  vendored here. tiktoken is a close proxy for a GPT-family BPE,
                  but treat counts as +/- a few percent.
  NOT VERIFIED    the price per token. Taken from issue #43 and NOT checked
                  against Groq's live price list -- re-check before quoting any
                  dollar figure in the paper.

Run:  venv/bin/python experiments/m5_4_latency_cost_breakdown.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import timeit
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.guardrails import inspect_alert
from src.agent.schema_guardrail import validate_field_types
from src.agent.fallback_classifier import _load_model, _to_feature_frame
from src.agent.mitre_lookup import get_technique_info, load_technique_map
from src.models.decision import resolve_label

OUT_JSON = Path("experiments/results/m5_4_latency_cost.json")
OUT_CSV = Path("experiments/results/m5_4_latency_cost.csv")

# From issue #43. NOT independently verified against Groq's price list.
PRICE_INPUT_PER_1M = 0.20
PRICE_OUTPUT_PER_1M = 0.20
PRICE_SOURCE = ("issue #43; not verified against Groq's live price list. "
                "Re-check before quoting a dollar figure.")

ALERTS_PER_DAY = 10_000
REPEATS, NUMBER = 7, 2_000

SAMPLE_ALERT = {
    "AlertTitle": 15723, "DetectorId": 7, "Category": "CredentialAccess",
    "MitreTechniques": "T1110;T1110.003", "SuspicionLevel": "Suspicious",
    "LastVerdict": "Suspicious",
}


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def best_micros(fn, number=NUMBER, repeats=REPEATS) -> float:
    """Best-of-N mean microseconds. Best-of, not mean-of-means: the minimum is
    the least contaminated by scheduler noise on a shared laptop."""
    timings = timeit.repeat(fn, number=number, repeat=repeats)
    return (min(timings) / number) * 1e6


def measure_stages() -> dict:
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]
    features = _to_feature_frame(dict(SAMPLE_ALERT), model, encoders)
    proba = model.predict_proba(features)[0]
    technique_map = load_technique_map()   # cache load excluded from the timing

    stages = {
        "guardrail_regex": best_micros(lambda: inspect_alert(SAMPLE_ALERT)),
        "guardrail_schema": best_micros(lambda: validate_field_types(SAMPLE_ALERT)),
        "feature_encode": best_micros(
            lambda: _to_feature_frame(dict(SAMPLE_ALERT), model, encoders), number=200),
        "rf_inference": best_micros(lambda: model.predict_proba(features), number=200),
        "tie_break_and_label": best_micros(lambda: resolve_label(model.classes_, proba)),
        "mitre_lookup_cached": best_micros(
            lambda: get_technique_info("T1110", technique_map), number=200),
        "hitl_gate": best_micros(
            lambda: (np.sort(proba)[::-1][0] - np.sort(proba)[::-1][1]) < 0.2),
    }
    return {k: round(v, 4) for k, v in stages.items()}


def llm_latency_from_committed() -> dict:
    w = json.loads(Path("experiments/results/week7_scalability_benchmark.json").read_text())
    single = [r for r in w["results"] if r["mode"] == "llm" and r["workers"] == 1]
    if not single:
        raise SystemExit("no single-worker LLM row in the week-7 benchmark")
    r = single[0]
    return {
        "mean_latency_seconds": r["mean_latency_seconds"],
        "mean_latency_micros": r["mean_latency_seconds"] * 1e6,
        "throughput_alerts_per_second": r["throughput_alerts_per_second"],
        "source": "experiments/results/week7_scalability_benchmark.json (workers=1)",
        "note": "remote inference plus network; reused rather than re-measured "
                "so this script costs no Groq quota",
    }


def token_estimate() -> dict:
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    from src.agent import nodes
    import inspect as _inspect
    src = _inspect.getsource(nodes.explain_with_llm)
    # The system prompt is a literal inside the node; take the longest literal as
    # a stand-in rather than re-declaring it here and letting the two drift.
    literals = [s for s in src.split('"""') if len(s) > 200]
    system_prompt = max(literals, key=len) if literals else ""
    user_payload = json.dumps(SAMPLE_ALERT)
    prompt_tokens = len(enc.encode(system_prompt)) + len(enc.encode(user_payload))
    # Completion length from the rationales actually produced in the 999-alert run.
    try:
        rows = json.loads(Path(
            "experiments/results/agent_metrics_week15_rf_primary.json").read_text()
        )["per_alert_results"]
        texts = [r.get("reasoning") or "" for r in rows if r.get("reasoning")]
        completion_tokens = int(np.median([len(enc.encode(t)) for t in texts])) if texts else 0
        completion_source = f"median over {len(texts)} committed rationales"
    except (FileNotFoundError, KeyError):
        completion_tokens, completion_source = 0, "unavailable"
    return {
        "tokeniser": "tiktoken o200k_base (proxy for openai/gpt-oss-20b)",
        "prompt_tokens_per_call": prompt_tokens,
        "completion_tokens_per_call": completion_tokens,
        "completion_source": completion_source,
        "caveat": "approximate; the deployed model's exact tokeniser is not vendored",
    }


def main() -> None:
    print("timing offline stages (best-of-7)...")
    stages = measure_stages()
    llm = llm_latency_from_committed()
    tok = token_estimate()

    fast_path_micros = sum(v for k, v in stages.items())
    routed_path_micros = fast_path_micros + llm["mean_latency_micros"]

    cost_per_call = (tok["prompt_tokens_per_call"] / 1e6 * PRICE_INPUT_PER_1M
                     + tok["completion_tokens_per_call"] / 1e6 * PRICE_OUTPUT_PER_1M)

    # The router sends only evidence-rich alerts to the LLM. 209 of 999 in the
    # committed control run.
    routed_fraction = 209 / 999
    cost_all_routed = ALERTS_PER_DAY * cost_per_call
    cost_with_router = ALERTS_PER_DAY * routed_fraction * cost_per_call

    result = {
        "experiment": "M5.2 PART B -- per-stage latency, throughput and API cost",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "timing_method": f"timeit best-of-{REPEATS}; machine-dependent, treat as "
                         "an order of magnitude",
        "per_stage_microseconds": stages,
        "llm_stage": llm,
        "end_to_end": {
            "fast_path_micros": round(fast_path_micros, 2),
            "fast_path_throughput_alerts_per_sec": round(1e6 / fast_path_micros, 1),
            "routed_path_micros": round(routed_path_micros, 2),
            "routed_path_throughput_alerts_per_sec": round(1e6 / routed_path_micros, 3),
            "llm_share_of_routed_path": round(llm["mean_latency_micros"] / routed_path_micros, 6),
        },
        "tokens": tok,
        "pricing": {
            "input_per_1m_usd": PRICE_INPUT_PER_1M,
            "output_per_1m_usd": PRICE_OUTPUT_PER_1M,
            "source": PRICE_SOURCE,
        },
        "cost": {
            "usd_per_llm_call": round(cost_per_call, 8),
            "alerts_per_day": ALERTS_PER_DAY,
            "usd_per_day_all_routed": round(cost_all_routed, 4),
            "router_routed_fraction": round(routed_fraction, 4),
            "usd_per_day_with_router": round(cost_with_router, 4),
            "router_cost_reduction_factor": round(
                cost_all_routed / cost_with_router, 2) if cost_with_router else None,
        },
    }
    OUT_JSON.write_text(json.dumps(result, indent=2) + "\n")
    pd.DataFrame([{"stage": k, "microseconds": v} for k, v in stages.items()]
                 + [{"stage": "llm_call", "microseconds": round(llm["mean_latency_micros"], 1)}]
                 ).to_csv(OUT_CSV, index=False)

    print("\n  per-stage (microseconds):")
    for k, v in sorted(stages.items(), key=lambda kv: -kv[1]):
        print(f"    {k:24} {v:>12,.2f}")
    print(f"    {'llm_call (committed)':24} {llm['mean_latency_micros']:>12,.0f}")
    e = result["end_to_end"]
    print(f"\n  fast path   : {e['fast_path_micros']:,.0f} us "
          f"-> {e['fast_path_throughput_alerts_per_sec']:,.0f} alerts/s")
    print(f"  routed path : {e['routed_path_micros']:,.0f} us "
          f"-> {e['routed_path_throughput_alerts_per_sec']:.3f} alerts/s")
    print(f"  LLM is {e['llm_share_of_routed_path']:.4%} of the routed path")
    c = result["cost"]
    print(f"\n  ${c['usd_per_llm_call']:.8f}/call; "
          f"{ALERTS_PER_DAY:,} alerts/day = ${c['usd_per_day_all_routed']:.2f} all-routed, "
          f"${c['usd_per_day_with_router']:.2f} with the router "
          f"({c['router_cost_reduction_factor']}x cheaper)")
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
