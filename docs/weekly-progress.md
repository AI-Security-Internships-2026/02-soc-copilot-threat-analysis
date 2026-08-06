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

### Next week plan
- Read the 5 papers identified this week
- Complete `docs/proposal.md` draft
- Set up dataset download / preprocessing pipeline

---

## Week 2

**Branch:** `asma-week-02`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/2

### Completed this week
- [x] Created `asma-week-02` branch from `dev`
- [x] Drafted `docs/proposal.md` (problem statement, research questions, methodology)
- [x] Built GUIDE dataset schema reference + synthetic sample generator (for local dev without the full Kaggle download)
- [x] Built data loader + preprocessing pipeline (feature engineering, encoding)
- [x] Built baseline Random Forest triage classifier (TP/BP/FP) with eval metrics
- [x] Wired `src/main.py` to run the full pipeline end to end — confirmed working
- [ ] Expand literature review to 10 papers/tools (in progress — completed Week 3, see below)
- [ ] Real GUIDE dataset download/preprocessing pipeline (currently running on synthetic sample — completed Week 4, see below)

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
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/8

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

## Week 8 — Issue #10: model-based guardrail investigation

**Branch:** asma-week-08
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/12

### Goal

Issue #10 asked for a second-stage ML classifier behind the regex guardrail,
to catch paraphrased/obfuscated injection attempts the regex fast-path can't
see. Ehsanullah's repo (`03-prompt-injection-detection`, his PR #10)
benchmarked Meta Llama Prompt Guard and Protect AI LLM Guard for this.

### Classifier selection

Pulled his benchmark data (`guardrail_comparison.json`, `eval_dataset_v2.csv`,
1000 rows, balanced) to compare all three candidates on the same numbers.
His own repo's TF-IDF + Logistic Regression detector actually beat both
frameworks he benchmarked:

| Detector | F1 | Median latency | Throughput |
|---|---|---|---|
| TF-IDF + LogReg | 0.883 | 0.79ms | 1258/s |
| Meta Llama Prompt Guard | 0.747 | 179ms | 5.6/s |
| Protect AI LLM Guard | 0.722 | 183ms | 5.5/s |

Went with TF-IDF + LogReg — best accuracy *and* three orders of magnitude
faster, no reason to pay the latency cost of the LLM-based options.

### Integration

Wired the detector in as a second guardrail stage (`src/agent/ml_guardrail.py`),
scoped to `AlertTitle`. Hit and fixed a real bug along the way: the pickled
model was trained under scikit-learn 1.7.1, the venv had 1.7.2 — cross-version
unpickling was silently producing non-deterministic scores run to run. Pinned
to 1.7.1, confirmed stable output.

### Finding that changed the plan

Once wired up and run against real GUIDE alert data, the detector blocked
**100% of alerts** (9/9 and 30/30 at both batch sizes tested). A single plain
benign sentence ("please schedule a team meeting for next Tuesday") scored
0.726 — well above the 0.5 flag threshold. A quick 5-title sanity check on
routine SOC alert titles confirmed it wasn't a fluke — all 5 scored above
threshold (0.524–0.945).

To get a real number instead of a gut check, built a 40-row synthetic
SOC-domain eval set (`experiments/soc_domain_eval_v1.csv`: 20 benign SOC
alert titles + 20 injection attempts phrased as alert-field text) and scored
it (`experiments/soc_domain_eval.py`).

### Bug found in review: wrong predict_proba index

Dr. Rana caught a real bug in `score_text()`: it read
`classifier.predict_proba(X)[0][0]` instead of `[0][1]`. The pickled model's
classes are `0 = Benign, 1 = Prompt Injection Attack` (per the original
`ml_detector.py` docstring), so the guardrail was reading P(benign) and
treating it as an injection score the whole time — exactly backwards. This
also explained the two most suspicious results in the first pass: the
clearest injection example scored lowest of all 40 rows, and a mundane
benign alert scored highest.

**Fixed:** flipped the index to `[0][1]`, and actually pinned
`scikit-learn==1.7.1` in `requirements.txt` (the earlier sklearn
version-mismatch fix had only been applied locally, not committed — also
caught in review).

### Corrected results

| | min | max | mean |
|---|---|---|---|
| benign | 0.021 | 0.608 | 0.209 |
| injection | 0.013 | 0.711 | 0.224 |

| threshold | accuracy | precision | recall | f1 |
|---|---|---|---|---|
| 0.5 | 0.500 | 0.500 | 0.150 | 0.231 |
| 0.6 | 0.500 | 0.500 | 0.050 | 0.091 |
| 0.7 | 0.525 | 1.000 | 0.050 | 0.095 |
| 0.8 | 0.500 | — | 0.000 | 0.000 |
| 0.9 | 0.500 | — | 0.000 | 0.000 |
| 0.95 | 0.500 | — | 0.000 | 0.000 |

Direction is corrected now — the clearest injection example (HTML-comment
override) scores highest (0.711) and the previously-inverted benign example
scores lowest (0.021), as expected. But the underlying finding barely
changes: best accuracy across the sweep is 52.5%, and at threshold 0.7+ the
detector predicts "injection" for essentially nobody (1 true positive out
of 20 actual injections at 0.7; zero at 0.8 and above). This isn't a
directionality problem anymore — the model outputs a narrow, low P(injection)
band for almost all structured alert-style text, whether the true label is
benign or attack. It has no working signal for this domain, not an inverted
one.

### Decision

Unchanged: not wiring the detector into the live pipeline as a hard gate.
`graph.py` still routes straight from `regex_guardrail` to
`fetch_mitre_context`. `src/agent/ml_guardrail.py` ships as tested
infrastructure — the index bug and the code are both fixed and correct now,
it's the training data that doesn't cover this domain.

### Next step for issue #10

Same as before, reinforced by the corrected numbers: needs a domain-specific
model or fine-tuning on SOC-style data. The near-zero signal here (rather
than a strong-but-wrong signal) makes it clearer this is a training-data gap,
not something threshold tuning or a bug fix can close. Worth flagging to
Dr. Rana before the Aug 9 stress-test milestone, since it assumes a working
second-stage classifier to stress-test.

## Week 9 — Issue #10: root cause found, classifier retired, schema guardrail shipped

**Branch:** `asma-week-09`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/15 (schema guardrail, merged Aug 2)
**Follow-up PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/17 (post-merge audit fix — graph-wiring regression, RF retrain, doc reconciliation; opened Aug 4, targets `dev`)

### Reframing the Aug 9 milestone
The roadmap's Aug 9 plan was to time-box a fine-tune/retrain of the Week 8
classifier on SOC-domain-labeled text. Before spending that time-box, checked
what AlertTitle actually contains in the real dataset — and it changes the
whole picture.

### Root cause: AlertTitle is a numeric ID field, not text
`schema.py` lists AlertTitle as categorical, and the GUIDE paper's own
description of the alert dataframe only names OrganizationId, DetectorId,
ProductId, Category, and Severity as categorical columns — no free-text
column exists in the schema at all. Confirmed directly against
`GUIDE_train.csv`: AlertTitle has 86,149 unique values, all plain integers
(sample: 45654, 99614, 111349, 56759, ...).

This means the Week 8 "domain mismatch" framing was correct in effect but
imprecise in cause. It wasn't that the classifier was trained on the wrong
*style* of SOC text — there's no text there to begin with. A TF-IDF
classifier can't find linguistic signal in a field that was never
linguistic. No amount of domain-matched training data would have closed
that gap, so retiring the fine-tune plan rather than time-boxing it — the
outcome was predictable from the schema alone, and confirming that in
advance saved the week rather than burning it on a doomed experiment.

### What replaced it: deterministic schema/type validation
Since AlertTitle (and DetectorId) are supposed to always be numeric IDs,
the correct second-stage check isn't a classifier — it's verifying the
field IS a valid integer. Any injection payload is, by definition, not a
valid integer, so this separates the two classes by construction rather
than by learned approximation.

`src/agent/schema_guardrail.py` implements this. Tested two ways:
- Synthetic: 20 realistic numeric IDs (benign) vs. the 20 injection strings
  from the Week 8 eval set (attack) — 100% accuracy, 0 false positives,
  0 false negatives.
- Real data: ran `validate_field_types` against 5,000 real AlertTitle
  values sampled from `GUIDE_train.csv` — **0 false positives**. The
  check doesn't misfire on real production-shaped values, not just the
  synthetic test case.

### Decision: hard-gated, unlike the Week 8 classifier
Wired into `graph.py` as an actual gate this time
(`regex_guardrail` → `schema_guardrail` → `fetch_mitre_context`). Safe to
hard-gate here in a way the ML classifier never was: this check has no
threshold, no accuracy tradeoff, no probabilistic gray zone — a value
either parses as an integer or it doesn't. `ml_guardrail.py` stays in the
repo, untouched, as tested infrastructure for a future dataset that has
an actual free-text field to defend.

### Problems / Blockers
None blocking. One open item: `DetectorId` is included in
`EXPECTED_NUMERIC_FIELDS` based on the GUIDE paper's description rather
than a direct check like AlertTitle got — confirmed — DetectorId values are small integers, not the large ID space the paper implied, but still integers, so no change needed to the check itself

### Next step for issue #10
Closed with a working fix. Reclaimed the Aug 9 time-box — putting the
freed time toward Aug 16 writeup prep instead, per the roadmap.

### Post-merge audit finding (Aug 2): graph wiring regression, fixed
A repo-wide consistency audit against this log found a real bug introduced
by this week's own schema-guardrail commit (`2975183`): wiring
`schema_guardrail` into `graph.py` deleted the conditional edge that used
to run `fetch_mitre_context → (classify_with_llm | rf_fallback)` via
`route_by_context`, and never replaced it. `route_by_context` stayed
defined and imported in `nodes.py` but nothing called it anymore.

The graph still compiled without error — LangGraph doesn't validate
dead-end nodes at compile time — and ran to completion, but silently
stopped after `fetch_mitre_context`. No `predicted_label`, `verdict`,
`confidence`, or `reasoning` was ever produced. This was invisible in
practice because `evaluate.py` reads the missing key with
`result.get("predicted_label", "FalsePositive")` — every alert would have
silently scored as a hardcoded `FalsePositive` guess instead of raising.
`src/app.py`, `benchmark.py`, and `run_agent.py` all invoke the same
compiled `triage_graph` and were equally affected. No `agent_metrics_real*`
file had been regenerated since the breaking commit landed (Jul 31 18:18),
so nothing had surfaced this — there was no automated test to catch it
either, since the repo had no `tests/` directory at all until now.

**Fix:** restored the `fetch_mitre_context → (classify_with_llm |
rf_fallback)` conditional edge in `graph.py`, so the schema guardrail now
sits correctly in front of the pre-existing LLM/RF routing instead of
replacing it: `regex_guardrail → schema_guardrail → fetch_mitre_context →
(llm | rf_fallback) → verdict routing → (end | human_review)`.

**Verification, not just claim:**
- Added `tests/` (new — none existed before): `test_graph_wiring.py`
  asserts every non-END node has an outgoing edge and that
  `fetch_mitre_context` reaches both classification paths, plus an
  end-to-end invoke on a sparse alert confirming a real `predicted_label`
  comes out. `test_schema_guardrail.py` and `test_ml_guardrail.py` turn
  this week's and last week's manual spot-checks (20v20 synthetic accuracy,
  the `[0][1]` predict_proba index fix) into assertions instead of prose.
  All 9 tests pass (`venv/bin/python3 -m pytest tests/ -v`).
- Re-ran `evaluate.py` post-fix on a fresh 30-alert sample
  (`experiments/results/agent_metrics_post_graph_fix_week9.json`):
  accuracy 0.533, macro F1 0.534, predictions spread across all three
  classes (12 BenignPositive / 10 TruePositive / 8 FalsePositive) with 9
  alerts routed through the LLM and 21 through the RF fallback — proof the
  graph is actually classifying again, not just returning a hardcoded
  default.
- Also found and fixed a related but separate issue while verifying:
  `experiments/results/baseline_model.joblib` (the RF artifact the
  fallback path loads) had been pickled under scikit-learn 1.7.2, one
  patch version ahead of the `1.7.1` pinned in `requirements.txt` since
  the Week 8 `ml_guardrail` fix — the same cross-version unpickling risk
  that caused non-deterministic scores there. Retrained it
  (`python -m src.models.baseline --force-retrain`) under the pinned
  version; macro F1 held at 0.751 (matching the prior artifact), and the
  `InconsistentVersionWarning` is gone.
- Reconciled `README.md`'s "Expected Deliverables" table, which still said
  the final report was due Week 8, against the "Roadmap to September 8"
  section actually being followed (report drafting Aug 30, final
  submission Sep 8). Also fixed a stale `STATUS = "Week 2..."` string in
  `src/main.py`.

## Scalability benchmark follow-up (2026-08-06): RF sweep completed, hybrid still blocked

Issue #16 / PR #18 flagged **E3 — "scalability benchmark table only
partially transcribed"** as a blocker for the paper's Evaluation section.
Checked `experiments/results/week7_scalability_benchmark.json` against the
Week 7 "next week plan" (rerun RF and hybrid across all three prompt-count
tiers): RF mode only had `prompt_count=30` (both worker counts), and
`hybrid` mode had zero entries at all, despite both being called for by the
rerun command documented in the Week 7 section itself.

**RF gap closed.** Re-ran `src.agent.benchmark --modes rf --prompt-counts
60 120 --workers 1 4 --append`, reusing the exact same cached balanced
sample (`guide_balanced_40_per_class_seed_42.csv`) the original Week 7 run
used, so the new rows are directly comparable to the existing ones rather
than drawn from a different sample. RF mode now has all six
prompt-count/worker combinations:

| Prompts | Workers | Alerts/s | Mean latency | Accuracy | Macro F1 | Core util % |
|---|---|---|---|---|---|---|
| 30 | 1 | 16.69 | 0.060s | 0.633 | 0.622 | 10.43 |
| 30 | 4 | 41.85 | 0.024s | 0.633 | 0.622 | 14.23 |
| 60 | 1 | 20.45 | 0.049s | 0.700 | 0.490 | 10.41 |
| 60 | 4 | 37.70 | 0.027s | 0.700 | 0.490 | 14.04 |
| 120 | 1 | 29.75 | 0.034s | 0.675 | 0.673 | 10.76 |
| 120 | 4 | 39.01 | 0.026s | 0.675 | 0.673 | 14.16 |

Throughput and per-core utilization stay in the same band as the original
30-prompt rows at every tier, and errors are 0 across the board — the
1-vs-4-worker speedup pattern from Week 7 holds at larger prompt counts
too, it just hadn't been measured there before.

One environment gap hit and fixed along the way: the first attempt at this
rerun failed 100% of requests with `Fallback model not found at
experiments/results/baseline_model.joblib` — that artifact and the GUIDE
CSVs are gitignored, so a fresh checkout of the repo doesn't have them.
Symlinked them in from an existing checkout that had already run
`src.models.baseline` and downloaded the dataset, discarded the corrupted
100%-error results, and reran cleanly. Documented here since anyone else
rerunning this benchmark from a clean clone will hit the same wall: the
Random Forest artifact must exist at `experiments/results/baseline_model.joblib`
before `--modes rf` (or `hybrid`) will produce real numbers instead of
silent failures.

**Hybrid mode still blocked — needs a `GROQ_API_KEY`.** Hybrid mode routes
part of its traffic to the live LLM (the Week 6 hybrid split was 244/300
alerts to the RF fallback, 56 to the LLM), and no Groq key is available in
this environment — no `.env` file, nothing exported in the shell. Running
`--modes hybrid` without one wouldn't just fail loudly; the LLM-routed
subset would fast-fail on an auth/connection error in milliseconds instead
of taking the real ~1.8–2.7s network round trip the LLM-only rows show, so
the resulting throughput and latency numbers would look artificially great
while being meaningless — exactly the "no rounded/fabricated metrics"
failure mode issue #16's checklist warns against. Left this untouched
rather than run it with fake numbers.

**To finish E3:** run
`venv/bin/python -m src.agent.benchmark --modes hybrid --prompt-counts 30 60 120 --workers 1 4 --append`
with a valid `GROQ_API_KEY` in `.env`, then update the Week 7 results table
above and in PR #18's transcription with the completed hybrid row.