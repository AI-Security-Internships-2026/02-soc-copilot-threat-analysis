"""
M6.1 PART A -- build PAPER_FIGURE_MANIFEST.md, mapping every paper table and
figure to the artifact it is read from and the command that regenerates it.

Issue #44. The manifest is generated rather than hand-written so two things stay
machine-checked instead of drifting: every source path it names must exist, and
every result JSON/CSV under experiments/results/ must be claimed by at least one
entry. A hand-maintained manifest silently rots the first time a result is added.

Run:  venv/bin/python experiments/m6_1_build_manifest.py
"""

import json
import subprocess
from pathlib import Path

RESULTS = Path("experiments/results")
OUT = Path("PAPER_FIGURE_MANIFEST.md")

# The clean-room reproducibility audit commit from M1.1 (docs/reproduce_from_scratch.log).
M1_SHA = "e126c1e193a016fb567cfb8371007372c4994902"

# tolerance rationale:
#   1e-4  -- deterministic, seeded, recomputed from a committed array
#   5e-3  -- depends on a live LLM call or an API-bounded sample
#   2e-2  -- wall-clock timing, machine dependent
DET, LLM, TIME = 1e-4, 5e-3, 2e-2

# (id, what it reports, source artifact(s), regeneration command, tolerance, reproduce cost)
ENTRIES = [
    ("Tab 1", "Pre-deployment classifier selection benchmark",
     ["soc_domain_eval_results.json"],
     "venv/bin/python experiments/soc_domain_eval.py", DET, "yes -- ~2 CPU-min, no API"),
    ("Tab 2", "SOC-domain threshold sweep, post index-bug fix",
     ["soc_domain_eval_results.json"],
     "venv/bin/python experiments/soc_domain_eval.py", DET, "yes -- ~2 CPU-min, no API"),
    ("Tab 3", "Random Forest baseline metrics (0.7718 / 0.7505)",
     ["baseline_metrics.json"],
     "venv/bin/python -m src.models.baseline", DET, "yes -- ~10 CPU-min, no API"),
    ("Tab 4", "Paired comparison on the identical 209-alert subset",
     ["rf_vs_llm_control.json", "llm_subset_eval_improved_full209.json"],
     "venv/bin/python experiments/rf_vs_llm_control.py", DET,
     "yes -- ~3 CPU-min, no API (LLM side is cached)"),
    ("Tab 5", "LLM accuracy by self-reported confidence band",
     ["rf_vs_llm_control.json"],
     "venv/bin/python experiments/rf_vs_llm_control.py", DET, "yes -- ~3 CPU-min, no API"),
    ("Tab 6", "RF margin-threshold sweep on the same 209 alerts",
     ["rf_vs_llm_control.json"],
     "venv/bin/python experiments/rf_vs_llm_control.py", DET, "yes -- ~3 CPU-min, no API"),
    ("Tab 7", "Whole-pipeline accuracy, before and after the architecture change",
     ["agent_metrics_week15_rf_primary.json", "archive/agent_metrics_week12_999_current.json"],
     "SOC_COPILOT_SKIP_EXPLANATION=1 venv/bin/python -m src.agent.evaluate "
     "--sample-size 999 --output experiments/results/agent_metrics_week15_rf_primary.json",
     DET, "yes -- ~7 CPU-min with the skip flag, no API"),
    ("Tab 8", "Scalability benchmark, LLM-only mode",
     ["week7_scalability_benchmark.json"],
     "venv/bin/python -m src.agent.benchmark --mode llm", TIME,
     "no -- ~40 min and ~2k Groq calls; timing is machine dependent"),
    ("Tab 9", "Scalability benchmark, RF-only mode",
     ["week15_rf_benchmark.json"],
     "venv/bin/python -m src.agent.benchmark --mode rf", TIME,
     "yes -- ~5 CPU-min, no API; timing is machine dependent"),
    ("Tab 10", "Input guardrail layers, measured separately",
     ["guardrail_layer_eval.json", "schema_guardrail_eval.json"],
     "venv/bin/python experiments/guardrail_layer_eval.py", DET, "yes -- <1 CPU-min, no API"),
    ("Tab 11", "Accuracy on train-sampled data vs. the held-out test split",
     ["guide_test_holdout_eval.json", "holdout_vs_train_symmetric_15000.json",
      "large_train_sampled_rf_eval.json"],
     "venv/bin/python experiments/guide_test_holdout_eval.py", DET,
     "yes -- ~8 CPU-min, no API"),
    ("Tab 12", "Control-node ablation arms at full n=999 scale",
     ["control_node_ablation.json"],
     "venv/bin/python experiments/control_node_ablation.py", LLM,
     "partial -- two arms are Groq-quota bounded; see Section 4.11 caveat"),
    ("Tab 13", "Accuracy by evidence bin at full scale",
     ["control_node_ablation.json"],
     "venv/bin/python experiments/control_node_ablation.py", LLM,
     "partial -- same quota bound as Tab 12"),
    ("Tab 14", "Contamination measured two ways (exact-row vs incident-level)",
     ["incident_leakage_audit.json", "overlap_audit.json", "m2_1_historical_eval_overlap.json"],
     "venv/bin/python experiments/incident_leakage_audit.py", DET,
     "yes -- ~25 CPU-min, streams GUIDE_train.csv"),
    ("Tab 15", "Accuracy on rows never trained on, by labelled-sibling availability",
     ["incident_leakage_audit.json", "m2_1_leakage_300k_balanced.json"],
     "venv/bin/python experiments/incident_leakage_audit.py", DET, "yes -- ~25 CPU-min"),
    ("Tab 16", "Held-out performance by training-slice size and estimator",
     ["classifier_improvement_study.json"],
     "venv/bin/python experiments/classifier_improvement_study.py", DET,
     "no -- ~3 CPU-hours and up to 8 GB RAM at the 2M-row arms"),
    ("Tab 17", "Identifier feature-inflation ablation",
     ["classifier_improvement_study.json"],
     "venv/bin/python experiments/classifier_improvement_study.py", DET,
     "no -- part of the Tab 16 run"),
    ("Tab 18", "Eight detectors on the 400-attack SOC injection benchmark",
     ["m3_2_heuristic_detectors.json", "m3_2_learned_detectors.json",
      "m3_1_benchmark_generation.json", "m3_2_familywise_failure_analysis.json"],
     "venv/bin/python experiments/m3_2_heuristic_detectors.py && "
     "venv/bin/python experiments/m3_2_learned_detectors.py", DET,
     "partial -- L3 needs OPENAI_API_KEY (--include-api); heuristics and L1/L2 run offline"),
    ("Fig 1", "Triage pipeline control flow (TikZ, transcribed from graph.py)",
     [], "n/a -- hand-transcribed from src/agent/graph.py, verified by tests/test_graph_wiring.py",
     DET, "n/a -- no numeric content"),
    ("Fig 2", "Benign-vs-injection score distribution",
     ["soc_domain_eval_results.json"],
     "venv/bin/python docs/paper/figures/generate_figures.py", DET, "yes -- <1 CPU-min"),
    ("Fig 3", "Throughput vs. worker count, faceted by pipeline mode",
     ["week7_scalability_benchmark.json", "week15_rf_benchmark.json"],
     "venv/bin/python docs/paper/figures/generate_figures.py", TIME, "yes -- <1 CPU-min"),
    ("Fig 4", "RF vs LLM accuracy comparison",
     ["rf_vs_llm_control.json"],
     "venv/bin/python docs/paper/figures/generate_figures.py", DET, "yes -- <1 CPU-min"),
    ("Fig 5", "LLM confidence calibration",
     ["rf_vs_llm_control.json"],
     "venv/bin/python docs/paper/figures/generate_figures.py", DET, "yes -- <1 CPU-min"),
    ("Fig 6", "Random Forest one-vs-rest ROC curves on GUIDE_Test",
     ["roc_auc_control_209.json", "guide_test_holdout_eval.json"],
     "venv/bin/python experiments/roc_auc_analysis.py && "
     "venv/bin/python docs/paper/figures/generate_figures.py", DET, "yes -- ~8 CPU-min"),
]

# Results that back the methodology rather than a specific table/figure. Listed so
# the "every artifact is claimed" check is real rather than satisfied by omission.
SUPPORTING = {
    "m2_1_splitmethod_delta_5seeds.json": "Sec 4.12 -- 7-seed replication of the split-rule gap",
    "grouped_split_baseline.json": "Sec 4.12 -- single-seed grouped-split baseline",
    "m2_2_kaggle_baselines.json": "Sec 4.12 -- third-party Kaggle notebook reproduction",
    "m2_2_kaggle_notebook_1.json": "Sec 4.12 -- Kaggle notebook 1, both split methods",
    "m2_2_kaggle_notebook_2.json": "Sec 4.12 -- Kaggle notebook 2, both split methods",
    "m2_3_grouped_deployed.json": "Sec 4.12 -- incident-grouped model deployment check",
    "m2_4_best_model_selection.json": "Sec 4.13 -- classifier suite selection",
    "m2_4_heldout_n15k.json": "Sec 4.13 -- classifier suite on held-out n=15,000",
    "m2_4_m3a_vs_m7_mcnemar.json": "Sec 4.13 -- paired McNemar across the suite",
    "m2_4_m7_llm_only.json": "Sec 4.13 -- LLM-only arm of the suite",
    "m2_4_validate_5seed.json": "Sec 4.13 -- 5-seed group-validation of the suite",
    "m3_1_benchmark_generation.json": "Sec 4.14 -- benchmark composition (also Tab 18)",
    "m3_2_familywise_failure_analysis.json": "Sec 4.14 -- 56-cell family-wise failure matrix",
    "verdict_invariance.json": "Sec 4.7 -- the explanation node cannot change a verdict",
    "field_inclusion_audit.json": "Sec 3.2 -- which fields reach the model",
    "m6_1_effect_sizes.json": "M6.1 PART C -- McNemar odds ratios and Holm-Bonferroni "
                              "correction backfilled for the compliance audit",
    "m6_3_ci_backfill.json": "M6.3 PART B -- percentile-bootstrap and Clopper-Pearson "
                             "CIs backfilled onto Sections 4.1-4.9 and Tab 18",
    "m5_1_burden_sweep.json": "M5.1 PART B -- HITL margin-threshold burden sweep on "
                              "the held-out 15,000",
    "m5_1_burden_sweep.csv": "M5.1 PART B -- the same sweep as a 9-row CSV for Figure 6",
    "m5_4_latency_cost.json": "M5.2 PART B -- per-stage latency, throughput and API cost",
    "m5_4_latency_cost.csv": "M5.2 PART B -- per-stage timing as a CSV",
    "deepteam_redteam_fullgraph_llm_reached.json": "Sec 4.9 -- adversarial red-team evaluation",
    "week15_rf_benchmark.json": "Tab 9 and Fig 3",
    "m2_1_overlap_scatter.csv": "Sec 4.12 -- 4-point overlap scatter (M2.1 Pearson)",
    "m3_1_rating_worksheet.csv": "M3.1 -- blind inter-rater worksheet for the benchmark",
    ".m3_1_rating_worksheet_key.csv": "M3.1 -- rater answer key; dot-prefixed so raters "
                                      "cannot see it while scoring the worksheet above",
}

# Artifacts that a still-open PR introduces. Listed so the cross-check does not
# report them missing on a branch that legitimately predates them.
PENDING = {
    "m4_1_security_asr_runner.json": "Sec 4.9 -- A3/A4 Triage-ASR; arrives with PR #50 (M4.1, issue #38)",
}


def git_sha():
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def build():
    missing, claimed = [], set()
    lines = [
        "# Paper Figure & Table Manifest",
        "",
        "Generated by `experiments/m6_1_build_manifest.py` (issue #44, M6.1 PART A).",
        "Do not edit by hand -- regenerate instead, or the cross-checks below stop meaning anything.",
        "",
        f"- **M1.1 clean-repro commit:** `{M1_SHA}`",
        f"- **Manifest generated at commit:** `{git_sha()}`",
        "- **Dataset integrity:** `datasets/INTEGRITY_MANIFEST.json`; verify with "
        "`venv/bin/python scripts/verify_data_integrity.py` before trusting any re-run.",
        "",
        "Tolerance is the absolute difference at which a regenerated figure should be "
        "treated as a mismatch rather than noise: `1e-4` for deterministic seeded "
        "recomputation, `5e-3` where a live LLM call or an API-bounded sample is "
        "involved, `2e-2` for wall-clock timing.",
        "",
        "## A. Tables and figures",
        "",
        "| ID | Reports | Source artifact(s) | Regenerate with | Tol | Reproducible? |",
        "|---|---|---|---|---|---|",
    ]
    for eid, what, sources, cmd, tol, cost in ENTRIES:
        for s in sources:
            claimed.add(s)
            if not (RESULTS / s).exists():
                missing.append((eid, s))
        src = "<br>".join(f"`experiments/results/{s}`" for s in sources) or "_n/a_"
        lines.append(f"| {eid} | {what} | {src} | `{cmd}` | {tol:g} | {cost} |")

    lines += ["", "## B. Supporting artifacts (methodology, not a numbered table)", "",
              "| Artifact | Supports |", "|---|---|"]
    for name, why in sorted(SUPPORTING.items()):
        claimed.add(name)
        if not (RESULTS / name).exists():
            missing.append(("supporting", name))
        lines.append(f"| `experiments/results/{name}` | {why} |")

    on_disk = {p.name for p in RESULTS.glob("*.json")} | {p.name for p in RESULTS.glob("*.csv")}
    unclaimed = sorted(on_disk - claimed)

    lines += ["", "## C. Pending -- introduced by an open PR, not yet on this branch", "",
              "| Artifact | Supports |", "|---|---|"]
    for name, why in sorted(PENDING.items()):
        claimed.add(name)
        state = "present" if (RESULTS / name).exists() else "not yet merged"
        lines.append(f"| `experiments/results/{name}` | {why} _({state})_ |")

    lines += ["", "## D. Cross-check", ""]
    lines.append(f"- Artifacts referenced by an entry: **{len(claimed)}**")
    lines.append(f"- Artifacts present under `experiments/results/`: **{len(on_disk)}**")
    if missing:
        lines.append(f"- **Referenced but missing from disk: {len(missing)}**")
        for eid, s in missing:
            lines.append(f"  - {eid} -> `{s}`")
    else:
        lines.append("- Referenced but missing from disk: **0**")
    if unclaimed:
        lines.append(f"- **Present but unclaimed: {len(unclaimed)}** "
                     "(add an entry, or move to `archive/` if superseded)")
        for s in unclaimed:
            lines.append(f"  - `{s}`")
    else:
        lines.append("- Present but unclaimed: **0**")

    OUT.write_text("\n".join(lines) + "\n")
    return missing, unclaimed


if __name__ == "__main__":
    miss, unclaimed = build()
    print(f"wrote {OUT}")
    print(f"  missing from disk : {len(miss)}")
    print(f"  unclaimed on disk : {len(unclaimed)}")
    for s in unclaimed:
        print(f"    unclaimed: {s}")
