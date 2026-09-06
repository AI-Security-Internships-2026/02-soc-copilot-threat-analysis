# Archived results — superseded, kept for provenance

These files are **not current** and none of them should be cited. They are retained
because the sequence of numbers is part of the project's record: several of the
project's findings are visible only as a change between two of these runs.

The authoritative artifact for each claim lives one directory up, in
`experiments/results/`.

## Why this directory exists

`experiments/results/` accumulated fourteen superseded result files alongside the
live ones, with no marker distinguishing them. Two specific hazards followed:

1. **`agent_metrics.json` is a synthetic-data run.** It reports accuracy 0.375 over
   48 alerts. Those alerts came from `datasets/sample/guide_sample.csv`, whose
   labels `src/data/generate_sample.py` assigns with `random.choices()`
   independently of every feature — so 0.375 is a draw from the class prior and
   measures nothing. Nothing in the file said so; it was structurally identical to
   a real result. (`src/agent/evaluate.py` now stamps a `data_source` block with an
   `is_synthetic` flag into every artifact it writes, so this cannot recur.)
2. **`agent_metrics_week12_999_current.json` is named "current" and is not.** It is
   the *before* side of the Week-15 architecture change.

## The `agent_metrics_*` lineage

Each row is the same evaluation as the pipeline evolved. Read top to bottom.

| file | date | n | accuracy | macro F1 | what it was |
|---|---|---|---|---|---|
| `agent_metrics.json` | 2026-06-24 | 48 | 0.375 | 0.347 | ⚠️ **SYNTHETIC DATA** — random labels, no signal. Not a result. |
| `agent_metrics_real.json` | 2026-07-03 | 300 | 0.4000 | 0.3862 | first run on real GUIDE data, LLM-only |
| `agent_metrics_real_v2.json` | 2026-07-13 | 300 | 0.2867 | 0.1751 | LLM-only, revised prompt |
| `agent_metrics_real_v3.json` | 2026-07-13 | 300 | 0.2800 | 0.1836 | LLM-only, same day as v2 |
| `agent_metrics_real_check.json` | 2026-07-26 | 300 | 0.4000 | 0.3861 | re-verification of `_real`; differs only in the 4th decimal of F1 |
| `agent_metrics_week6_fallback.json` | 2026-07-15 | 300 | 0.7533 | 0.7500 | RF fallback introduced; 81% of alerts routed to the RF |
| `agent_metrics_week6_fallback_rerun.json` | 2026-07-26 | 999 | 0.6737 | 0.6694 | same design at 999; used the since-retired `llama-3.1-8b-instant` |
| `agent_metrics_post_graph_fix_week9.json` | 2026-08-02 | 30 | 0.5333 | 0.5337 | 30-alert smoke run after the graph-wiring fix |
| `agent_metrics_week12_999_current.json` | 2026-08-29 | 999 | 0.6456 | 0.6484 | the **"before"** in the 0.6456 → 0.7347 architecture-change claim |

**Superseded by:** `../agent_metrics_week15_rf_primary.json` (n=999, accuracy 0.7347,
macro F1 0.7307) — the RF-decides/LLM-explains architecture.

## LLM prompt comparison

| file | date | n | accuracy | macro F1 | what it was |
|---|---|---|---|---|---|
| `llm_subset_eval_baseline.json` | 2026-08-26 | 60 | 0.2833 | 0.1511 | original prompt, 60-alert pilot |
| `llm_subset_eval_improved.json` | 2026-08-26 | 60 | 0.3333 | 0.2679 | improved prompt, 60-alert pilot |

**Superseded by:** `../llm_subset_eval_improved_full209.json` — the full 209-alert
run of the improved prompt, which is what `rf_vs_llm_control.py` and
`roc_auc_analysis.py` read.

## Red-team runs

| file | date | attacks | passed | failed | errored | what it was |
|---|---|---|---|---|---|---|
| `deepteam_redteam_results.json` | 2026-08-25 | 12 | 7 | 0 | 5 | LLM node only, first pass |
| `deepteam_redteam_promptinjection_retry.json` | 2026-08-21 | 12 | 4 | 0 | 8 | prompt-injection-focused retry; more errors than the original |
| `deepteam_redteam_fullgraph_results.json` | 2026-08-21 | 12 | 9 | 0 | 3 | ⚠️ **invalid** — Week 11 found the attacks never reached the LLM; every alert was routed to the RF, so this measured nothing about the LLM's resistance |

**Superseded by:** `../deepteam_redteam_fullgraph_llm_reached.json` — the full-graph
run after the routing gap was fixed and the attacks demonstrably reached the LLM.

## A note on `../baseline_metrics.json`

That file is **live**, not archived, but it predates the provenance fields
`src/models/baseline.py` now writes (`data_source`, `split`). Its 0.7718 accuracy is
a genuine 19,895-row holdout, but from a **row-level** split of the same 100,000-row
slice the model trained on. GUIDE's label is incident-level, so sibling rows of one
incident sit on both sides of that boundary. See
`../grouped_split_baseline.json` for what the split rule is worth, and
`../incident_leakage_audit.json` for the underlying measurement.
