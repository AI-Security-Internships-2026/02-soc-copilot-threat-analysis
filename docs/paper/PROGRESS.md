# Paper Progress Tracker — Issue #16 (Springer IJIS submission, due 2026-09-08)

**Issue:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/issues/16
**Working draft:** `docs/paper/draft.md` (Markdown content draft — not yet in journal template)
**Branch:** `worktree-paper-draft-issue-16` (created from `origin/asma-week-09`, which is PR #17 / unmerged into `dev` as of 2026-08-04 — see "Branch note" below)
**Last worked:** 2026-08-04

Read this file first when picking this up again. It tells you what's done, what's half-done, and exactly where to resume.

---

## How the sections map to issue #16's checklist

| Issue #16 item | Status | Where |
|---|---|---|
| Abstract (250 words) | Draft written (~230 words) | `draft.md` §Abstract |
| I. Introduction | Draft written | `draft.md` §I |
| II. Related Work | Draft written, citations need author-list verification | `draft.md` §II |
| III. Proposed Method | Draft written, fully grounded in code + PRs | `draft.md` §III |
| IV. Evaluation | Draft written, **2 open reconciliation items (E2–E3 below); E1 resolved 2026-08-04** | `draft.md` §IV |
| V. Discussion | Draft written | `draft.md` §V |
| VI. Conclusion | Draft written (short — expand after IV/V settle) | `draft.md` §VI |
| References (≥20, majority 2023–2026) | 17 sourced and real, not fabricated. **Need 3–4 more + author verification** (R1, R2 below) | `draft.md` §References |
| Use journal's LaTeX/Word template | **Not started** (T1 below) | — |
| All tables/figures referenced in text | Tables are inline in Markdown and referenced; figures **not started** — no plots generated yet (T2) | — |
| Results match committed files exactly | E1 fully resolved (both halves committed); E2 still open | — |
| Commit draft to `docs/paper-draft.pdf` | **Not started** — draft is still `.md`, needs template + PDF export (T1) | — |
| Open PR against `dev` | **Not started** | — | 

---

## Open items to resolve before this is submission-ready

### Evaluation (E)
- **E1 — DONE (2026-08-04).** `experiments/schema_guardrail_eval.py` writes `experiments/results/schema_guardrail_eval.json`. Both halves are now committed: synthetic 20v20 (100% accuracy) and the real-data half (5,000 `AlertTitle` values from `datasets/GUIDE_train.csv`, 0 false positives) — the dataset was symlinked into this worktree from the main checkout to run it. `draft.md` §4.3 updated to cite the populated result instead of the PR #15 description, and the corresponding stale bullet removed from §V Limitations. **Caveat added to Limitations:** the script reads the first 5,000 rows in file order, not a random sample — flagged honestly rather than overclaiming "random sample."
- **E2 — Two end-to-end agent-eval files disagree and aren't reconciled.** `agent_metrics_post_graph_fix_week9.json` (n=30, post graph-wiring fix, acc 0.5333/F1 0.5337) vs. `agent_metrics_real_v3.json` (n=300, acc 0.28/F1 0.1836, against a *different* RF baseline comparison number in the same file: 0.374/0.296 — note this doesn't match `baseline_metrics.json`'s 0.7718/0.7505 either, which needs explaining, not just citing). Action: figure out which of `agent_metrics_real*.json` (there are 5: `real`, `real_check`, `real_v2`, `real_v3`, plus `week6_fallback` and `week6_fallback_rerun`) is the authoritative current-pipeline number, why the RF baseline comparison differs by file (different sample/seed?), and either rerun a single fresh large-sample eval post-graph-fix or explain the discrepancy explicitly in the Evaluation section rather than picking whichever number is more flattering.
- **E3 — Scalability benchmark table is only partially transcribed.** `week7_scalability_benchmark.json` has full CPU/memory/worker-scaling rows beyond what's in the draft (only regex microbenchmark + 1-worker LLM row are in `draft.md` §4.6 currently). Action: transcribe the full `results` array into a proper table, and decide whether it needs a figure (e.g., throughput vs. worker count) — see T2.

### References (R)
- **R1 — Need 3–4 more references to hit the ≥20 minimum with majority 2023–2026.** Candidates already identified and listed at the bottom of `draft.md` §References (MITRE ATT&CK text-tagging paper, alert-fatigue survey, adaptive incident prioritization paper, sklearn/TF-IDF methodology citation, GUIDE Kaggle release). Pull these in and verify them the same way as R2.
- **R2 — Author-list verification.** References 6, 9–17 in the current draft were found via web search and have verified titles/venues/arXiv IDs/years, but several are missing full author lists (marked `[AUTHORS TO VERIFY]` inline). Before submission, pull each from arXiv/publisher metadata directly (e.g., `arxiv.org/abs/<id>`) to get the real author list — do not guess or omit authors to save time.

### Template and artifacts (T)
- **T1 — No LaTeX/Word template applied yet.** Need to get Springer's official IJIS author template (Springer Nature's unified LaTeX class, typically `sn-jnl.cls`, or check IJIS's specific instructions-for-authors page in case it differs) and port `draft.md` into it section by section. This is the single largest remaining task.
- **T2 — No figures yet.** At minimum: (a) pipeline architecture diagram for §III.1 (the `START → ... → END` graph is currently ASCII in the Markdown — needs a real figure), (b) a bar/box plot of benign-vs-injection score distributions for §IV.2 (the table exists, a plot would strengthen the "no usable signal" claim visually), (c) throughput-vs-worker-count plot from the full scalability data (E3).
- **T3 — Word count / page budget check.** Draft has not been checked against an 8–10 page Springer two-column (or single-column, template-dependent) budget. Do this once T1 is done, not before — page count is meaningless in Markdown.

---

## What's solid and doesn't need rework
- The core narrative (Sections III–V) is fully grounded in real, checked artifacts: `src/agent/schema_guardrail.py`, `src/agent/graph.py`, `src/agent/ml_guardrail.py`, PRs #12/#14/#15/#17, and `docs/weekly-progress.md` Weeks 8–9. No numbers in III/V were invented.
- Section IV's tables 4.1–4.4 and 4.6 (partial) are transcribed directly from committed JSON files with the source file named next to each table — safe to carry forward as-is.
- The Related Work framing (issue #16 asked specifically for LlamaFirewall, Prompt Guard, LLM Guard, and MITRE-ATT&CK-grounded LLM systems) is covered with real sources, not generic filler.

## Branch note
This work started on a worktree branch reset to `origin/asma-week-09` (PR #17, open against `dev`, not yet merged as of 2026-08-04) rather than `dev` directly, because `asma-week-09` has the graph-wiring fix and regression tests this paper describes in §III.4 — `dev` doesn't have them merged yet. **Before opening the final PR for this paper against `dev`, check whether PR #17 has merged.** If it has, rebase this branch onto current `dev`. If not, either wait or open the paper PR with a note that it depends on #17 landing first, since §III.4's narrative assumes that fix exists in the codebase the paper describes.

## Suggested next session's first move
Pick E1 (cheapest, most valuable — turns a PR-prose claim into a real committed artifact) or R1/R2 (reference cleanup, no code needed) depending on whether you want to work in the repo or just do citation research.
