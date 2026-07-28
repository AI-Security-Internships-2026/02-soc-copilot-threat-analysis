# Weekly Progress Log: SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Student:** Asma
**GitHub username:** urpinklipbalm

---

## How to Use This File

Add a new section every Friday before opening your weekly Pull Request.
Be honest — problems and blockers are normal and help your supervisor support you.

---

## Week 1

**Branch:** `asma-week-01`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/1

### Completed this week
- [x] Read README and proposal
- [x] Set up local environment (Python venv, dependencies)
- [x] Wrote personal introduction (below)
- [x] Identified 3 related papers / tools / datasets
- [x] Run starter script (`python src/main.py`) — confirmed working

### Personal Introduction
I'm Asma, a third-year BS Computer Science student at NUST SEECS, Islamabad. My background is in Python, PyTorch, scikit-learn, LangChain, and the Groq API, with projects spanning anomaly detection, LLM-based apps, and graph-based systems. I'm particularly interested in how LLMs can assist SOC analysts in alert triage and threat correlation. Through this internship I hope to build practical experience in AI-assisted blue team operations and understand real-world SOC workflows.

### Problems / Blockers
System defaulted to Python 2.7 via pyenv — resolved by using `python3 -m venv venv` instead.
System defaulted to Python 2.7 via pyenv — resolved by using `python3 -m venv venv` instead.

### Next week plan
- Read the 5 papers identified this week
- Complete `docs/proposal.md` draft
- Set up dataset download / preprocessing pipeline

---

## Week 2

**Branch:** `asma-week-02`
**PR link:** _[Add link after opening PR]_

### Completed this week
- [x] Created `asma-week-02` branch from `dev`
- [x] Drafted `docs/proposal.md` (problem statement, research questions, methodology)
- [x] Built GUIDE dataset schema reference + synthetic sample generator (for local dev without the full Kaggle download)
- [x] Built data loader + preprocessing pipeline (feature engineering, encoding)
- [x] Built baseline Random Forest triage classifier (TP/BP/FP) with eval metrics
- [x] Wired `src/main.py` to run the full pipeline end to end — confirmed working
- [ ] Expand literature review to 10 papers/tools (in progress)
- [ ] Real GUIDE dataset download/preprocessing pipeline (currently running on synthetic sample)

### Problems / Blockers
Hit a merge conflict in `docs/weekly-progress.md` after stashing local changes across a branch switch — resolved by manually merging the conflicting "Next week plan" section.

### Next week plan
- Continue triage agent implementation (LangGraph)
- Architecture design doc (due Week 3)
- Expand literature review toward 10 papers/tools (carried over)

---

## Week 3

**Branch:** `asma-week-03`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/3

### Completed this week
- [x] Built 3-node LangGraph pipeline: `build_context` → `classify_with_llm` → `parse_verdict`
- [x] Switched LLM backend to Groq (`llama-3.1-8b-instant`) after hitting OpenAI quota limits
- [x] Structured JSON-only prompting for reliable verdict/confidence/reasoning parsing
- [x] Ran agent evaluation on synthetic sample: macro F1 0.347 vs RF baseline 0.296 (+0.051), with zero training data
- [x] Fixed categorical column auto-detection bug in `preprocess.py` (`df.select_dtypes(include="object")`)
- [x] Fixed import name mismatch in `evaluate.py`
- [x] Expanded literature review to 10 entries

### Problems / Blockers
PR #3 was accidentally merged into `main` instead of `dev`. Dr. Rana approved it anyway, but this needs to be corrected in Week 4 by targeting `dev` for all future PRs.

### Next week plan (per Dr. Rana's feedback)
- Add human-review checkpoint node with conditional routing
- Test on the real GUIDE dataset (not just the synthetic sample)

---

## Week 4

**Branch:** `asma-week-04`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/4

### Completed this week
- [x] Added human-review checkpoint node with conditional routing — alerts with confidence != "high" get flagged (`needs_human_review: True`) and routed through a review node instead of auto-closing
- [x] Built MITRE ATT&CK RAG integration — new `fetch_mitre_context` node looks up real technique descriptions from the MITRE ATT&CK dataset and injects them into the LLM's prompt context
- [x] Built Streamlit demo UI (`src/app.py`) — paste alert fields, click "run triage", see verdict/confidence/reasoning/review flag
- [x] Fixed baseline accuracy key bug in `evaluate.py` (was looking for `"accuracy"` at the top level; actual key is nested under `"classification_report"`)
- [x] Added CLI args (`--sample-size`, `--output`) to `evaluate.py` for flexible evaluation runs
- [x] Ran full evaluation on real GUIDE dataset (300 rows, stratified across all 3 classes) — results below
- [x] Updated literature review date and fixed remaining placeholder details
- [x] Updated `datasets/README.md` download date placeholder

### Results — real GUIDE dataset (300 rows, 100 per class)

| Metric | RF baseline | Week 3 agent (synthetic) | Week 4 agent (real data) |
|---|---|---|---|
| Accuracy | 0.374 | 0.375 | 0.400 |
| Macro F1 | 0.296 | 0.347 | 0.386 |

Agent beats RF baseline by +0.090 macro F1 on real data — an improvement over the +0.051 margin seen on the synthetic sample in Week 3.

Per-class breakdown: BenignPositive has high precision (0.64) but low recall (0.21) — the agent is often correct when it says "benign" but misses a lot of actual benign cases, likely misclassifying them as FalsePositive (which shows the opposite pattern: 0.34 precision, 0.61 recall).

### Problems / Blockers
None blocking — the real-data evaluation confirmed the agent generalizes well beyond the synthetic sample.

### Next week plan
- Investigate the BenignPositive/FalsePositive confusion pattern — possibly a prompt refinement
- Continue expanding real-dataset evaluation to a larger sample if time allows
- Address any remaining supervisor feedback from Week 4 PR review

---

## Week 5

**Branch:** `asma-week-05`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/5

### What I did
Dr. Rana's ask for this week was to check whether class imbalance in the 300-row eval
sample was causing BenignPositive to be under-predicted. Went digging into evaluate.py
and the actual sample first, before touching any code.

Turned out the sample isn't imbalanced at all - evaluate.py deliberately draws exactly
100 rows per class (min(100, len(class_df)), random_state=42), and I confirmed that
against the actual saved results: 100/100/100 exactly. Also checked the full 9.5M-row
GUIDE_train.csv distribution directly, and BenignPositive is actually the most common
class overall (4.1M rows), not the rarest. So the imbalance theory doesn't hold up.

Went looking for the real cause in the per-alert reasoning logs instead. Found that 186
out of 300 alerts (62%) get a "not enough information" type of reasoning from the LLM -
happens whenever MITRE technique / suspicion level fields are missing on the alert. Of
those 186 sparse-context alerts, the model defaults to FalsePositive 156 times (84%),
regardless of what the alert actually was. Ground truth for those same 186 alerts is
mostly not FalsePositive (74 BenignPositive, 58 FalsePositive, 54 TruePositive) - so
BenignPositive takes the biggest hit just because it's the largest chunk of that sparse
bucket.

Tried fixing this with two different prompt rewrites telling the model not to default
to FalsePositive when context is sparse, and to reason from what IS present instead of
what's missing. Both made things meaningfully worse - not because the fix was ignored,
but because the model just swapped its lazy default from FalsePositive to BenignPositive
instead. In both reruns, FalsePositive precision and recall dropped to 0.00 - the model
almost stopped predicting it entirely (v2: 91/100 and 79/100 TruePositive/FalsePositive
alerts misclassified as BenignPositive respectively; v3: similar). Macro F1 dropped from
0.386 (original prompt) to 0.175 and 0.184 for the two attempts.

Reverted back to the original prompt since it's still the best-performing version. Kept
both failed experiment result files (agent_metrics_real_v2.json, _v3.json) in the PR as
evidence of what was tried and why it didn't work.

### Results summary
| version | accuracy | macro F1 | FalsePositive precision/recall |
|---|---|---|---|
| original prompt (week 4) | 0.400 | 0.386 | 0.34 / 0.61 |
| v2 (sparse-context fix, prefer BenignPositive) | 0.287 | 0.175 | 0.00 / 0.00 |
| v3 (evidence-based reasoning fix) | 0.280 | 0.184 | 0.00 / 0.00 |

### Problems / Blockers
The root cause looks less like a prompt wording issue and more like a model capacity
limitation - llama-3.1-8b-instant seems to fall back on a single dominant guess for
low-context alerts rather than actually weighing evidence per-alert, and changing the
wording just moves which label it defaults to. Prompt tuning alone doesn't seem to be
enough to fix this.

### Next week plan
Waiting on Dr. Rana's input on how to proceed - possible directions are adding a few
worked examples to the prompt (few-shot) instead of instructions, or testing whether a
larger/different model handles the sparse-context alerts better. Not going to keep
iterating on plain prompt wording without direction, since two attempts already showed
it just shifts the bias rather than fixing it.

---

## Week 6

**Branch:** `asma-week-06`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/6

### Root cause recorded from Week 5
The failure is a **sparse-context collapse**, not a class-imbalance issue. The
evaluation sample is balanced (100 examples per class), but 186/300 alerts (62%)
do not include enough of the prompt's discriminative evidence — MITRE technique,
suspicion level, or last verdict. For these alerts, the LLM receives mostly opaque
numeric GUIDE values and responds with an unsupported default label rather than a
per-alert decision. With the original prompt that default was FalsePositive
(156/186 sparse alerts); the two prompt variants merely moved the default to
BenignPositive. Their macro F1 scores (0.175 and 0.184) remain below both the
original LLM result (0.386) and the RF baseline (0.296).

### Targeted fix implemented
- [x] Added a **gated Random Forest fallback** for alerts with fewer than two of
  `MitreTechniques`, `SuspicionLevel`, and `LastVerdict` populated. These are the
  alerts where the LLM lacks analyst-readable evidence; alerts with richer context
  continue through the LLM and MITRE-enrichment path unchanged.
- [x] The fallback uses the RF baseline artifact (classifier plus its fitted
  categorical encoders) and recreates its saved feature order plus timestamp
  features. It returns the RF probability, route, and context-signal count in the
  graph state for auditability. The baseline must be regenerated once to replace
  the older classifier-only artifact.
- [x] Low-probability fallback outcomes still pass through the existing human-review
  checkpoint. A missing or incompatible fallback model fails safely to human review
  rather than substituting a label.
- [x] Extended evaluation logs with the route taken and fallback probability so the
  next run can report overall and sparse-alert performance separately.

### Validation completed
Trained a reusable 100k-row RF artifact and evaluated the hybrid on a fresh,
class-balanced 300-alert real-GUIDE sample. The evaluation records its route and RF
probability per alert, and future runs cache the evaluation sample after one streamed
pass through GUIDE rather than loading the entire dataset into memory each time.

### Results — fallback evaluation (300 balanced real GUIDE alerts)

| Metric | Week 5 best LLM-only prompt | Week 6 hybrid | 100k-row RF baseline |
|---|---:|---:|---:|
| Accuracy | 0.400 | 0.753 | 0.772 |
| Macro F1 | 0.386 | 0.750 | 0.751 |

The Week 6 hybrid is within 0.001 macro F1 of the RF baseline, a large improvement
over prompt-only variants (0.175–0.386). The fallback handled 244/300 alerts (81.3%)
with 82.0% accuracy; the LLM retained the richer-context route for 56 alerts. This
is evidence that the targeted fallback addresses sparse-context collapse, but it is
not evidence that the hybrid outperforms the RF baseline. Future evaluation runs
cache the small balanced sample after one streamed pass through GUIDE, avoiding a
full in-memory load on every experiment.

---

## Week 7

**Branch:** `asma-week-07`
**PR link:** _[add link after opening PR — base `dev`, compare `asma-week-07`]_

### Completed this week
- [x] Added a deterministic regex input guardrail that runs before either automated
  route (LLM or RF). Detects common prompt-injection/role-impersonation patterns
  and oversize text fields, and routes matches straight to human review without
  exposing the text to the LLM or RF classifier.
- [x] Added `src/agent/benchmark.py`, which records prompt count, worker count,
  wall time, throughput, process CPU time, per-core utilization estimate, peak
  RSS memory, routing outcomes, errors, and scored accuracy/F1 for RF, LLM, and
  hybrid modes.
- [x] Measured RF and hybrid throughput with 30 balanced GUIDE alerts using one
  and four workers. RF improved from 16.69 to 41.85 alerts/s (1.80s → 0.72s);
  the four-worker run used about 14.23% of the available eight logical cores.
- [x] Microbenchmarked the regex guardrail: 4.076 microseconds per check across
  10,000 benign and 10,000 injection-like inputs; it blocked 10,000/10,000 of
  the injection test inputs and 0/10,000 benign inputs.
- [x] Completed the live LLM latency/throughput benchmark after Groq connectivity
  was restored. The initial run showed heavy rate-limiting at `workers=4`
  (15–52 of N requests failing with `429`), which made concurrency look like
  it helped when it was actually just dropping requests faster. Fixed in a
  separate branch (`asma-week-07-llm-retry`, not bundled into this PR) by
  retrying 429s using the wait time Groq's own error message provides,
  instead of failing immediately.

  After the fix, errors dropped to 0–2 per run (down from 15–52), and
  `workers=1` vs `workers=4` wall time converged to nearly identical —
  confirming the earlier "speedup" from more workers was an artifact of
  dropped requests, not real concurrency, since all workers share the same
  per-minute token budget.

| Mode | Workers | Alerts/s | Mean latency | Completed | Errors |
|---|---|---|---|---|---|
| LLM | 1 | 0.37–0.57 | 1.8–2.7s | 30/30, 60/60, 120/120 | 0 |
| LLM | 4 | 0.37–0.37 | 2.7–2.7s | 30/30, 60/60, 118/120 | 0, 0, 2 |
| RF | 4 | 41.85 | — | — | 0 |

RF remains ~75–110x faster than LLM regardless of worker count — expected,
since RF is local CPU inference and LLM involves remote network calls plus
per-token generation, both gated by Groq's free-tier rate limit.

Results are saved in `experiments/results/week7_scalability_benchmark.json`.
To rerun the local/hybrid cases:

```bash
venv/bin/python -m src.agent.benchmark --modes rf hybrid --prompt-counts 30 60 120 --workers 1 4
```

After confirming Groq connectivity, rerun the LLM cases separately with the
same prompt counts and workers so remote inference latency is comparable.

### Problems / Blockers
Spent a significant chunk of this week untangling a branching mistake rather
than writing new code. Summary (full detail kept in a separate session log,
not duplicated here):

- Week 7 work (guardrail, benchmark script, new result JSONs) was built and
  left uncommitted on the old, already-merged `asma-week-06` branch instead of
  a fresh branch off `dev`.
- While fixing that, discovered a second, unrelated issue: a local-only commit
  (`fix: --force-retrain wasn't actually retraining`) existed on local `dev`
  but had never been pushed or merged — it wasn't on `origin/dev` at all.
  Investigated it and confirmed the bug it fixed had already been solved a
  different way by the Week 6 RF-fallback rewrite of `baseline.py`
  (`expected_metadata()` / `load_reusable_artifact()`), so the old fix was
  obsolete and was discarded (branch deleted locally and on origin) rather
  than merged, to avoid regressing the Week 6 provenance-checking logic.
- Also found two unused, harmless branches on origin — `revert-6-asma-week-06`
  and `revert-3-asma-week-03` — created by GitHub's "Revert" button at some
  point but with no PR ever opened from either. Confirmed via the Pull
  Requests tab that no PR exists for them, so they're inert. Left alone
  rather than deleted, since this is a shared repo — didn't want to remove
  something a collaborator or Dr. Rana might still reference.
- Once `dev` was confirmed clean and up to date with `origin/dev`, recreated
  `asma-week-07` from the correct base and reapplied the stashed Week 7 work.
  Verified no leftover conflict markers and reviewed the one incidental diff
  (trailing whitespace in `baseline_metrics.json`, not a data change) before
  committing.

### Next week plan
Rerun the LLM-vs-RF-vs-hybrid latency comparison once Groq is reachable, to
get a full throughput/latency picture across all three paths instead of just
RF and hybrid. Also: delete stale local branches (`asma-week-05`,
`asma-week-06`) now that Week 7 is pushed cleanly off current `dev`.
