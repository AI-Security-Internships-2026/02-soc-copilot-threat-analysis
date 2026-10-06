# experiments/m5_1_consolidate_ablation.py
#
# Issue #42 PART A, final consolidation. Reads the committed ablation,
# burden-sweep and latency artifacts -- no scoring, no LLM calls -- and emits
# the five-configuration table plus the per-component interpretation the issue
# asks for.
#
# Why this is a separate script rather than more output from
# m5_1_ablation_3missing.py: the five rows do not all come from the same run.
# Three were measured by that script, one is the Full reference it also
# measured, and the fifth (no-LLM-explanation) is established by Section 4.11's
# control-node ablation on a *different* evaluation sample. Keeping the
# consolidation separate is what lets each row carry its own provenance instead
# of inheriting one run's header.
#
# The trap this script exists to avoid: Section 4.11 arm (b) reports accuracy
# 0.7347 at n=999, but that sample is drawn from GUIDE_train.csv -- the file the
# classifier was trained on -- and is incident-level contaminated. The three new
# configs are on the held-out balanced 15K. Putting 0.7347 in the same accuracy
# column as 0.6998 would silently mix a contaminated figure with a clean one,
# which is the exact error class this project has spent two milestones removing.
# So the no-LLM row carries the held-out number it shares with Full by
# construction, and 0.7347 appears only as a cross-reference.
#
# usage (from repo root):
#   venv/bin/python experiments/m5_1_consolidate_ablation.py

from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RESULTS = Path("experiments/results")
ABLATION = RESULTS / "m5_1_ablation_5config.json"
BURDEN = RESULTS / "m5_1_burden_sweep.json"
LATENCY = RESULTS / "m5_4_latency_cost.json"
CONTROL = RESULTS / "control_node_ablation.json"
OUT_JSON = RESULTS / "m5_1_ablation_consolidated.json"
OUT_CSV = RESULTS / "m5_1_ablation_consolidated.csv"
OUT_MD = Path("docs/m5-1-ablation-interpretation.md")


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"{path} missing -- run its generator first")
    return json.loads(path.read_text())


def main() -> None:
    ablation, burden, latency, control = _load(ABLATION), _load(BURDEN), _load(LATENCY), _load(CONTROL)
    configs = ablation["configs"]
    full = configs["full"]

    sweep = burden.get("sweep") or burden.get("rows") or []
    t0 = next((r for r in sweep if r["T"] == 0.0), None)
    if t0 is None:
        raise SystemExit("burden sweep has no T=0 row to cross-check nohitl against")

    # Mati's item 2 cross-check, asserted rather than asserted-in-prose. T=0 and
    # "no HITL gate" are the same configuration reached two different ways, so
    # if these ever disagree one of the two runs is wrong.
    nohitl = configs["nohitl"]
    crosscheck = {
        "claim": "nohitl (ablation) and T=0 (burden sweep) are the same configuration",
        "ablation_accuracy": nohitl["accuracy"],
        "burden_t0_accuracy": t0["auto_accepted_accuracy"],
        "ablation_auto_accept": nohitl["auto_accept_pct"],
        "burden_t0_auto_accept": t0["auto_accepted_pct"],
        "agrees": (
            nohitl["accuracy"] == t0["auto_accepted_accuracy"]
            and nohitl["auto_accept_pct"] == t0["auto_accepted_pct"]
        ),
    }
    if not crosscheck["agrees"]:
        raise SystemExit(f"nohitl does not match burden-sweep T=0: {crosscheck}")

    guardrail = ablation["guardrail_tpr"]
    explanation = ablation["explanation_study"]
    arm_b = control["arms"]["b"]["metrics"]["overall"]
    llm_ms = latency["llm_stage"]["mean_latency_seconds"] * 1000.0

    def row(name: str, removed: str, src: dict, **over) -> dict:
        base = {
            "config": name,
            "component_removed": removed,
            "evaluation_set": ablation["evaluation_set"],
            "n": src["n_scored"],
            "accuracy": src["accuracy"],
            "accuracy_ci_lower": src["accuracy_ci"][0],
            "accuracy_ci_upper": src["accuracy_ci"][1],
            "macro_f1": src["macro_f1"],
            "delta_acc_vs_full": round(src["accuracy"] - full["accuracy"], 6),
            "auto_accept_pct": src["auto_accept_pct"],
            "delta_auto_accept_vs_full": round(src["auto_accept_pct"] - full["auto_accept_pct"], 6),
            "latency_p50_ms": src["latency_p50_ms"],
            "guardrail_attack_tpr": None,
            "d1_groundedness": None,
            "d2_mitre_match": None,
            "provenance": "experiments/m5_1_ablation_3missing.py, this run's own measurement",
        }
        base.update(over)
        return base

    rows = [
        row("full", "-- (reference)", full,
            guardrail_attack_tpr=guardrail["full"]["tpr"],
            d1_groundedness=explanation["full"]["d1_grounded_rate"],
            d2_mitre_match=explanation["full"]["d2_mitre_match_rate"]),
        row("no_llm_explanation", "explain_with_llm", full,
            latency_p50_ms=round(full["latency_p50_ms"] - llm_ms, 3),
            guardrail_attack_tpr=guardrail["full"]["tpr"],
            d1_groundedness="n/a -- no explanation is produced",
            d2_mitre_match="n/a -- no explanation is produced",
            provenance=(
                "Classification metrics are Full's, and identically so by construction: the "
                "15K classification pass already runs with SOC_COPILOT_SKIP_EXPLANATION=1, "
                "because explain_with_llm cannot write predicted_label. Section 4.11 arm (b) "
                f"verified this empirically on its own sample ({arm_b['n_scored']} alerts, "
                f"accuracy {arm_b['accuracy']}, 0 verdict mismatches vs the explanation-on arm). "
                "That 0.7347 is NOT reproduced in the accuracy column above: it is measured on a "
                "GUIDE_train-sampled set with incident-level contamination, so it is not "
                "comparable with the held-out figures here. Latency is Full's p50 minus the "
                f"measured LLM stage ({llm_ms:.0f} ms, m5_4_latency_cost.json)."
            )),
        row("nomitre", "fetch_mitre_context", configs["nomitre"],
            guardrail_attack_tpr=guardrail["full"]["tpr"],
            d1_groundedness=explanation["nomitre"]["d1_grounded_rate"],
            d2_mitre_match=explanation["nomitre"]["d2_mitre_match_rate"]),
        row("noguardrails", "H1 regex / H2 schema / H3 SOC-aware", configs["noguardrails"],
            guardrail_attack_tpr=guardrail["noguardrails"]["tpr"]),
        row("nohitl", "HITL review gate (T=0)", nohitl,
            guardrail_attack_tpr=guardrail["full"]["tpr"]),
    ]

    out = {
        "experiment": "M5.1 PART A -- consolidated 5-configuration ablation (issue #42)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "sources": {
            "classification_and_explanation": str(ABLATION),
            "hitl_crosscheck": str(BURDEN),
            "llm_stage_latency": str(LATENCY),
            "no_llm_empirical_reference": str(CONTROL),
        },
        "reference_config": "full",
        "nohitl_vs_burden_sweep_t0": crosscheck,
        "configs": rows,
        "explanation_proxy_caveat": ablation["explanation_proxy_caveat"],
    }
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")

    fields = [k for k in rows[0] if k != "provenance"]
    with open(OUT_CSV, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"saved {OUT_JSON}")
    print(f"saved {OUT_CSV}")
    print(f"nohitl == burden-sweep T=0: {crosscheck['agrees']}")
    for r in rows:
        print(f"  {r['config']:20s} acc={r['accuracy']} dacc={r['delta_acc_vs_full']:+.4f} "
              f"auto={r['auto_accept_pct']} guardrail_tpr={r['guardrail_attack_tpr']}")


if __name__ == "__main__":
    main()
