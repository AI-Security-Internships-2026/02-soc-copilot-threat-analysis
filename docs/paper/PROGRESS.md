# Paper Progress Tracker — Issue #16 (Springer IJIS submission, due 2026-09-08)

**Issue:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/issues/16
**PR:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/18 (draft, opened 2026-08-04 — stacked on unmerged #17, see "Branch note" below; not ready for merge, R1/R2/E2/E3/T2/T3 still open)
**Working draft:** `docs/paper/draft.md` (Markdown content draft) + `docs/paper/latex/ijis-draft.tex` (LaTeX port, started 2026-08-04, T1)
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
| Use journal's LaTeX/Word template | **In progress (T1 below)** — full section-by-section port done and compiling; not submission-ready (blocked on R1/R2/E2/E3/T2/T3) | `docs/paper/latex/ijis-draft.tex` |
| All tables/figures referenced in text | Tables ported to LaTeX (`booktabs`) and referenced; figures **not started** — no plots generated yet, pipeline diagram still ASCII-in-`verbatim` (T2) | — |
| Results match committed files exactly | E1 fully resolved (both halves committed); E2 still open | — |
| Commit draft to `docs/paper-draft.pdf` | **Started** — `docs/paper/latex/ijis-draft.pdf` compiles cleanly (verified with `tectonic`) from the new LaTeX source; not yet copied/renamed to the final `docs/paper-draft.pdf` path since content isn't submission-ready | `docs/paper/latex/ijis-draft.pdf` |
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
- **T1 — IN PROGRESS (started 2026-08-04).** Springer Nature's unified LaTeX class (`sn-jnl.cls`, all `sn-*.bst` styles, `sn-article.tex` sample) pulled into `docs/paper/latex/` from a mirror of Springer Nature's public LaTeX author package (godkingjay/springer-nature-latex-template on GitHub; same package Overleaf's gallery serves). `draft.md` has been ported section-by-section into `docs/paper/latex/ijis-draft.tex` — Abstract through Conclusion, all 5 tables (booktabs, set as full-width `table*` for the two-column layout), Declarations, and all 17 references (`references.bib`, `[AUTHORS TO VERIFY]` flags carried over honestly, not resolved — still R2). Compiles cleanly with zero warnings-of-substance using `tectonic` (self-contained LaTeX engine, `brew install tectonic`); verified by rendering the PDF and confirming a proper two-column Springer layout with working numbered citations (~8 pages). Documentclass is `[pdflatex,sn-basic,Numbered,iicol]{sn-jnl}` (Springer Basic numbered style, two-column) — inferred from third-party template aggregators (scispace, docx2latex) reporting this as IJIS's style, since IJIS's own instructions-for-authors page on link.springer.com requires an institutional login this session doesn't have and could not be fetched directly. **Treat this as a strong guess, not confirmed** — recheck against the actual gated page (or ask a co-author/supervisor with access) before submission. **Not done:** Section III.1's pipeline diagram is still ASCII wrapped in a `verbatim` figure, not a real vector diagram (T2a); no author-contribution/funding/ethics text beyond "Not applicable" placeholders — needs real content once co-authors (if any) and funding source are confirmed; page/word budget not checked (T3, deliberately deferred until content settles per R1/R2/E2/E3); author byline (`Asma Imran`, TECIP/Scuola Superiore Sant'Anna) was inferred from `docs/proposal.md` ("Student: Asma") and the README's project banner, not independently confirmed — verify before submission.
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
E1 and the initial LaTeX port (T1) are both done as of 2026-08-04. Next: either R1/R2 (reference cleanup — add the 3–4 missing citations and verify all `[AUTHORS TO VERIFY]` author lists, no code needed, can be done directly in `docs/paper/latex/references.bib`) or E2 (reconcile the two disagreeing end-to-end agent-eval files — needs a decision about which sample is authoritative, possibly a fresh eval run). T2 (figures) is easiest to pick up once E3's full scalability table is transcribed, since T2c depends on it.
