# Stale numeric claims audit — M1.2 Part A (issue #30)

Generated 2026-09-06 on branch `week17-submission-prep` at `e126c1e`.

## Scope and method

The stale-value set from the issue is **S = {0.7718, 0.7505, 0.7347, 3.616, `"p_value": 0.0`}**, searched across tracked `*.md`, `*.json`, `*.txt` and `*.py`.

**94 hits** across **22 files**, plus one value that no longer occurs at all.

## The classification rule used

Not every occurrence of a stale value is a stale claim, and treating them alike would have corrupted the evidence base. Three categories:

1. **Result artifacts (`experiments/results/**/*.json`) — never edited.** `0.7718` is the genuine measured accuracy of the row-level-split baseline. Overwriting it inside the artifact would falsify a measurement to make prose look better. What is stale is how a *document* presents that number, never the number in its own file.
2. **Code comments and docstrings — never edited.** These record provenance, typically saying that a value *was* superseded. `src/models/decision.py` and `experiments/guardrail_layer_eval.py` are examples.
3. **Prose in `*.md` — audited individually** and annotated or corrected.

## `"p_value": 0.0` — zero hits

This value does not occur anywhere in the repository. The paired McNemar result is reported as an exact binomial p-value, `4.66e-12`, in `experiments/results/rf_vs_llm_control.json` and in every document that cites it. The issue's expected replacement (`4.657e-12`) is the same figure at one more significant digit; the repository's own value is read directly from `scipy.stats.binomtest`, and is left as-is so that documents and artifact agree.

## `3.616` — the regex guardrail microbenchmark

Corrected. `3.616 µs` was a July constant that survived into Week 15 prose after the benchmark was re-run. The current measured figures come from `experiments/results/guardrail_layer_eval.json`: **1.93 µs** for a short alert and **5.56 µs** for a full injection-bearing alert, timed with `timeit`. Two documents quoted the stale value and both were corrected in Week 17 (`docs/final-report.md`, `docs/weekly-progress.md`). The remaining hits are the artifact that legitimately records the old benchmark (`week7_scalability_benchmark.json`) and comments explaining the supersession.

## `0.7718` / `0.7505` / `0.7347` — train-sampled figures

These are **not wrong**; they are correct measurements on data that is **incident-level contaminated**. `0.7718`/`0.7505` are the RF baseline's accuracy and macro F1 on a *row-level* holdout of the slice it trained on; `0.7347` is the whole-pipeline accuracy on a 999-alert sample of the training file.

Week 17 measured what that is worth: GUIDE's label attaches to the incident, not the alert row, and **55.8%** of a train-sampled evaluation set shares an incident with training. A row whose incident was seen in training scores **0.8332** against **0.5898** for one whose incident was not — **+24.3 points**, 95% CI [+0.2282, +0.2587] (`experiments/results/incident_leakage_audit.json`).

**The corrected held-out figure is 0.6998** (macro F1 0.6949, macro AUC 0.8775) on Microsoft's own `GUIDE_Test.csv` split at n=15,000 (`experiments/results/guide_test_holdout_eval.json`).

Under an incident-level split the baseline itself falls from 0.7718/0.7505 to **0.7435/0.7118**, a delta of −0.0283, 95% CI [+0.0199, +0.0368] (`experiments/results/grouped_split_baseline.json`).

## Prose hits — individual decisions

47 of the 94 hits are prose in `*.md`. Annotating all 47 would have made the
documents harder to read, not more honest, so each was judged on whether the
surrounding text already carries the caveat.

**Seven sites presented a contaminated figure with no nearby caveat and were
corrected:**

| file | what it was | what was done |
|---|---|---|
| `docs/proposal.md` (RQ1 answer) | Gave `0.6456 → 0.7347` and never mentioned the held-out figure anywhere | Annotated `[STALE: ...]` and the 0.6998 held-out result added |
| `docs/final-report.md` §5.1 | Baseline table `0.7718`/`0.7505` with no note that the holdout is row-level | Paragraph added pointing to §5.10's 0.7435 and the +24.3-point measurement |
| `docs/final-report.md` §5.4 | `+8.9 points` stated as the architecture result | Noted the absolute levels are train-sampled; the paired *gain* is unaffected |
| `docs/final-report.md` Conclusion | Closed on `0.6456 → 0.7347` uncaveated | Held-out 0.6998 added inline |
| `docs/project-explained.md` §8 | `0.7718` called "a genuine +34 points" | Incident-level result (0.7435/0.7118) added |
| `docs/project-explained.md` §12 | `+8.9 points` table, no caveat | Annotated `[STALE: ...]` |
| `docs/project-explained.md` one-paragraph summary | The standalone-quotable passage, closing on 0.7347 | Rewritten to lead with 0.6998 and the leakage finding |

**The remaining 40 prose hits were left as-is**, in four groups:

1. **Sites that already state the caveat in the adjacent sentence** — `README.md`
   line 29, `docs/final-report.md` §5.8/§5.10, `docs/demo-runbook.md` Step 7 and
   the closing script. Adding `[STALE: ...]` next to an explanation of the
   staleness would be noise.
2. **Sites whose entire subject is the contamination** — e.g.
   `docs/final-report.md` §5.10's comparison table, which exists to show
   `0.7718 → 0.7435`. The number must appear for the section to make sense.
3. **Verbatim expected terminal output** in `docs/demo-runbook.md`, which must
   match what the command actually prints.
4. **The weekly log**, which is an append-only historical record. A Week 15 entry
   correctly records what was believed in Week 15; Week 17's entry records the
   correction. Rewriting earlier entries would destroy the audit trail that makes
   the log useful.

## Re-run

After the edits, every remaining hit is one of: a result artifact, a code
comment, an intentional `[STALE: ...]` annotation, an adjacent-caveat site, or a
historical log entry. There are no uncaveated presentations of a contaminated
figure as a generalisation estimate left in the repository.

## Full hit table

| file | line | value | action | rationale |
|---|---|---|---|---|
| `README.md` | 29 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/demo-runbook.md` | 244 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/demo-runbook.md` | 251 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/demo-runbook.md` | 316 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/demo-runbook.md` | 372 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/demo-runbook.md` | 381 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/demo-runbook.md` | 386 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 36 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 39 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 45 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 223 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 224 | `0.7505` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 314 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 319 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 319 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 360 | `3.616` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 415 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 470 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 471 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 475 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 536 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 616 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 624 | `0.7505` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 624 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 628 | `0.7505` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 628 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 714 | `0.7505` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 714 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/final-report.md` | 879 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 367 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 368 | `0.7505` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 534 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 539 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 540 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 703 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 703 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 704 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 705 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/project-explained.md` | 755 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/proposal.md` | 103 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 295 | `3.616` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 1523 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 1571 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 1670 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 1763 | `3.616` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 1906 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2023 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2039 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2164 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2219 | `3.616` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2293 | `0.7347` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2363 | `0.7505` | SEE BELOW | Prose — audited individually. |
| `docs/weekly-progress.md` | 2363 | `0.7718` | SEE BELOW | Prose — audited individually. |
| `experiments/control_node_ablation.py` | 611 | `0.7347` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/grouped_split_baseline.py` | 3 | `0.7718` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/grouped_split_baseline.py` | 4 | `0.7505` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/grouped_split_baseline.py` | 26 | `0.7718` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/grouped_split_baseline.py` | 32 | `0.7718` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/grouped_split_baseline.py` | 88 | `0.7718` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/grouped_split_baseline.py` | 89 | `0.7505` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
| `experiments/guardrail_layer_eval.py` | 22 | `3.616` | NO ACTION | Appears in a comment explaining that 3.616 was the superseded July constant. The code itself computes the current figure. |
| `experiments/guardrail_layer_eval.py` | 94 | `3.616` | NO ACTION | Appears in a comment explaining that 3.616 was the superseded July constant. The code itself computes the current figure. |
| `experiments/results/agent_metrics_week15_rf_primary.json` | 3 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/agent_metrics_week15_rf_primary.json` | 5 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/archive/README.md` | 39 | `0.7347` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/README.md` | 41 | `0.7347` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/README.md` | 101 | `0.7718` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/agent_metrics_post_graph_fix_week9.json` | 5 | `0.7505` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/agent_metrics_week12_999_current.json` | 5 | `0.7505` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/agent_metrics_week6_fallback.json` | 5 | `0.7505` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/agent_metrics_week6_fallback_rerun.json` | 5 | `0.7505` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/control_node_ablation_two_proportion_tests.json` | 14 | `0.7347` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/control_node_ablation_two_proportion_tests.json` | 29 | `0.7347` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/archive/control_node_ablation_two_proportion_tests.json` | 59 | `0.7347` | NO ACTION | Archived artifact. Superseded by design and already marked not-citable in `experiments/results/archive/README.md`. |
| `experiments/results/baseline_metrics.json` | 2 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/baseline_metrics.json` | 28 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/control_node_ablation.json` | 26 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/control_node_ablation.json` | 202 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/control_node_ablation.json` | 289 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/control_node_ablation.json` | 413 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 22 | `0.7718` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 23 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 28 | `0.7718` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 30 | `0.7718` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 38 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 40 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 79 | `0.7718` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 93 | `0.7505` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/grouped_split_baseline.json` | 106 | `0.7718` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/guide_test_holdout_eval.json` | 21 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/guide_test_holdout_eval.json` | 28 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/guide_test_holdout_eval.json` | 40 | `0.7347` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `experiments/results/week7_scalability_benchmark.json` | 13 | `3.616` | NO ACTION | Measured value inside a result artifact. The number is correct for the experiment that produced it; rewriting it would falsify the artifact. Staleness is a property of how prose *presents* it, not of the measurement. |
| `src/models/decision.py` | 19 | `0.7347` | NO ACTION | Appears in a docstring/comment documenting provenance, not as a reported result. |
