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

---

## Week 10 — Wazuh integration research, GeNIS dataset research, literature review finalized

**Branch:** `asma-week-10`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/20 (merged)

Direction for this week came out of a supervisor meeting: investigate Wazuh, look for a newer
(2025+) SOC-related dataset — specifically one covering SME network traffic, since the project has
only ever evaluated against one static 2024 GUIDE snapshot — and finalize the literature review.
This replaces the roadmap's previous Aug 16 milestone ("write up domain-mismatch finding"); that
writeup now follows this week's work instead of preceding it (see updated `README.md` roadmap).

### Literature review: fixed a fabricated citation, added 3 new 2025+ sources
Auditing `docs/literature-review.md` end-to-end (not just adding to it) surfaced a real problem:
Paper 3 cited "Ferrag et al., arXiv 2407.08628" — that arXiv ID doesn't correspond to that paper at
all. Verified the actual Ferrag et al. record and found the real paper is arXiv 2405.12750,
"Generative AI in Cybersecurity: A Comprehensive Review of LLM Applications and Vulnerabilities" —
corrected the entry (title, method, dataset, relevance fields all updated to match the real paper,
which is a broader LLM-in-cybersecurity survey rather than a SIEM-triage-specific one).

Added three new entries found while researching Wazuh and 2025+ datasets:
- **Paper 6 — Wazuh RAG-Driven SOC Copilot** (MDPI *Sensors* 2025): the closest architectural match
  found in the literature — same LLM+RAG-over-alerts pattern as this project's LangGraph+MITRE-RAG
  pipeline, but grounded in live Wazuh alerts instead of a static dataset. Directly informed this
  week's adapter design (below).
- **Paper 7 — GeNIS Dataset** (Silva et al., *Data in Brief*, Mar 2025): a labeled dataset built
  specifically to address the scarcity of SME-network-traffic datasets — the closest real match to
  the "SME traffic" dataset gap flagged for this week.
- **Paper 8 — AI-Driven Security Alert Screening Survey** (Ndichu et al., arXiv 2605.08316,
  submitted to ACM Computing Surveys): reviews 22 benchmark/alert-level datasets by
  representational gaps vs. real SOC environments — the reference point used to evaluate whether
  GeNIS is actually worth adopting as a second dataset (see below).

### Wazuh: research + prototype adapter
Full write-up in `docs/wazuh-integration.md`. Summary: no live Wazuh server was deployed this week
(a full indexer/server/dashboard Docker stack is real infrastructure work, scoped out — see "Next
steps" below). Instead, documented Wazuh's alert JSON schema and built
`src/integrations/wazuh_adapter.py`, a pure mapping function translating a Wazuh alert dict into
this pipeline's existing `raw_alert` shape:
- `rule.id` → both `AlertTitle` and `DetectorId` (Wazuh's numeric rule ID is the closest analogue
  to both GUIDE fields, which issue #10's root-cause investigation found are numeric IDs, not
  text — Wazuh doesn't separate the two concepts the way GUIDE's schema happens to)
- `rule.mitre.id` → `MitreTechniques`, `rule.groups` → `Category`
- `rule.level` (0–15) bucketed into `SuspicionLevel` (low/medium/high)
- `LastVerdict` left unset — no live-alert equivalent of GUIDE's historical analyst verdict

Smoke-tested a mapped alert directly through `apply_regex_guardrail` → `apply_schema_guardrail` →
`build_context` (no changes made to `graph.py`, `nodes.py`, or either guardrail) — passed both
guardrails cleanly and produced a normal context block, confirming the adapter is sufficient
without touching the pipeline itself. `tests/test_wazuh_adapter.py` (4 tests) covers the field
mapping, the missing-MITRE case, severity bucketing, and asserts mapped output passes
`validate_field_types()` unchanged.

### GeNIS dataset: documented as a candidate, not yet integrated
Added a full entry to `datasets/README.md` following the existing GUIDE-entry template — source,
license (to verify on download), size, format, and an explicit note that GeNIS's flow-level
network schema doesn't map onto GUIDE's incident/alert schema, so integrating it would need its
own loader (`src/data/genis_schema.py`-equivalent) rather than extending `load_data.py`. Not
downloaded or wired into training/eval this week — flagged as a decision that needs sign-off
(which pipeline stage would GeNIS feed?) before committing a week to building a second loader path.

### Problems / Blockers
None blocking. Two things intentionally left as open decisions rather than resolved unilaterally:
1. GeNIS integration approach (second eval dataset vs. a separate flow-level pre-filter stage) —
   needs a decision before implementation, not a default guess.
2. Whether Wazuh integration continues toward a real Docker deployment next, or stays adapter-only
   pending the paper writeup timeline.

### Next steps
- If Wazuh continues: stand up a single-node Docker Wazuh stack, enroll at least one agent, and
  replace the hand-written sample alerts in `tests/test_wazuh_adapter.py` with real generated ones.
- If GeNIS is approved: build `src/data/genis_schema.py` + a loader mirroring `load_data.py`'s
  structure, download the real dataset per `datasets/README.md`'s policy (never commit raw data).
- Aug 16 writeup milestone now follows this week's work — see updated `README.md` roadmap.

### Post-work audit: verified this week's claims and re-checked older ones, unbiased pass
Before writing the paper draft, went back through the repo's actual claims — not just re-reading
docs, but reproducing numbers and independently re-verifying citations, including ones already on
`dev` before this week. Results:

**Held up under direct reproduction:**
- `AlertTitle` really is 86,149 unique plain integers in the real 9.5M-row `GUIDE_train.csv`
  (issue #10's root-cause claim) — re-checked directly against the file, exact match.
- RF baseline macro F1 — forced a full retrain (`--force-retrain`) rather than trusting the saved
  artifact; reproduced macro F1 0.751 exactly.
- PR #14's predict_proba `[0][0]`→`[0][1]` fix and the 52.5% best-accuracy figure — confirmed
  against the actual diff and `experiments/results/soc_domain_eval_results.json`'s sweep data.
- PR #17's graph-wiring regression and fix — confirmed against `git show` on the breaking and
  fixing commits directly; current `graph.py` wiring is correct.
- `agent_metrics_post_graph_fix_week9.json`'s accuracy/macro-F1/routing numbers — every figure in
  the doc matches the file exactly.

**Corrected (not fabrications, but wrong as stated):**
- Literature review Paper 2 (ADStrike): doc described it as generic "agentic pentesting" — it's
  specifically an Active Directory red-team framework. Corrected.
- Literature review Paper 5: doc listed the venue as MDPI *Informatics* — it's actually the
  *Journal of Cybersecurity and Privacy*, a different MDPI journal sharing a similarly-numbered
  ISSN pattern. Corrected. (Authors, volume/issue/DOI were all already right.)

**New finding — RF fallback path is unvalidated for Wazuh-origin alerts** (own new code, this
week): documented in `docs/wazuh-integration.md`'s new "Known limitation" section. Doesn't error,
but a sparse Wazuh alert leaves ~62% of the RF model's expected features as NaN — a distribution
the model was never validated against, distinct from GUIDE's own (smaller, in-distribution)
sparsity pattern. Not fixed this week (would require alert-origin tracking through `graph.py`
routing); documented as a scoped follow-up rather than patched quickly.

**Residual gap, not this week's code:** `evaluate.py`'s `result.get("predicted_label",
"FalsePositive")` default (the exact mechanism PR #17 found silently masking the graph-wiring
regression) is still there — PR #17 fixed the root cause (the missing edge) but not this masking
behavior itself. The only thing standing between a future routing regression and another silent
FalsePositive-default incident is remembering to run `tests/test_graph_wiring.py`. Flagging as a
defense-in-depth gap worth a follow-up, not fixed here to avoid touching shared evaluation code
outside this week's scope without discussion first.

**Separately flagged, not a code issue:** three already-merged commits on `main` (`7cbc58b`,
`ad02c85`, `61ea961`, all part of PR #17) carry AI co-authorship trailers, which conflicts with
the project's no-AI-attribution policy. Rewriting merged/shared history needs an explicit decision
before doing anything about it — noted for Dr. Rana rather than acted on unilaterally.

---

## Week 11 — deepteam red-team evaluation of the LLM triage node

**Branch:** `asma-week-11`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/22 (merged)

Not on the original roadmap — new scope, prompted by wanting to close a real, previously-flagged
gap: the project's only adversarial-input testing (`experiments/soc_domain_eval.py`) has only ever
scored a static 40-row hand-written set against the now-retired ML guardrail, never against the
actual LLM triage node (`classify_with_llm`). Given today falls inside the roadmap's Aug 23 buffer
week, this was deliberately time-boxed rather than left open-ended, with the Aug 30 draft deadline
in mind.

### deepteam integration

Full design rationale, exact scope, and results are in `docs/redteam-deepteam-eval.md` — not
duplicated here. Summary: wired [deepteam](https://github.com/confident-ai/deepteam) to dynamically
red-team `classify_with_llm` in isolation (guardrails bypassed on purpose — those are already
tested elsewhere), using a custom `GroqDeepEvalModel` wrapper (`src/agent/deepteam_groq_model.py`)
as both judge and attack-simulator model so no OpenAI key was needed, consistent with the Week 3
move off OpenAI. Scope: 3 vulnerabilities (`Robustness/hijacking`, `GoalTheft/social_engineering`,
`IndirectInstruction/cross_context_injection`) × 4 attacks (`PromptInjection`, `Base64`, `ROT13`,
`Roleplay`), mapped onto `soc_domain_eval_v1.csv`'s existing five-category taxonomy.

**Result: 12 test cases, 7 completed cleanly, all 7 resisted (0% attack success rate on conclusive
cases).** The other 5 errored — all on `PromptInjection`/`Roleplay` specifically (the two attack
methods whose "enhance" step needs the judge model to produce structured JSON), while `Base64` and
`ROT13` (deterministic transforms, no judge call needed) completed 3/3 each with zero errors.
Reproduced one instance with `ignore_errors=False`: `openai/gpt-oss-20b` (the Groq judge model)
produced a malformed JSON response, and deepteam's `attack_simulator.py` swallows the real exception
behind a generic `"Error enhancing attack"` label (bare `except:`). This is a judge-model
reliability limitation, not evidence about the target's safety either way — an errored case is
inconclusive, not a pass. (See "Follow-up" below: later work found this diagnosis, while plausible,
wasn't fully confirmed for all 5 cases.)

### Follow-up: retry attempts and a Groq daily-quota wall

Tried to close the `PromptInjection`/`Roleplay` gap same-day. First, reran with more attempts and
more internal retries, no code change — result was **worse** (0/12 conclusive), and the generic
error labels didn't reveal enough detail to confirm it was the same JSON-formatting cause rather
than something else. Then built real defensive handling: `GroqDeepEvalModel._ensure_valid_json()`
strips markdown fences and, if needed, makes one self-repair call asking the model to fix its own
malformed JSON, with 5 new mocked pytest cases (11/11 passing, no live calls). Re-running to verify
this live surfaced the actual cause of the retry's failure: Groq's daily token quota for
`openai/gpt-oss-20b` was exhausted (`Limit 200000, Used 198919`, confirmed via the literal 429
response) from cumulative testing that same day — every retry call failed immediately on rate limit,
before the new JSON-repair logic ever got to run. **So the fix is code-complete and unit-tested, but
not yet live-verified**, and the original diagnosis above should be read as "leading hypothesis,"
not confirmed root cause, for all 5 original errors. The original 7/12 result is unaffected by any
of this — it ran before the quota was exhausted.

### Production model deprecation found and fixed (blocking discovery, not planned)

While validating the deepteam wrapper against a live Groq call, hit a 404: `llama-3.1-8b-instant` —
the model hardcoded into the **production** `classify_with_llm` node since Week 3 — has been
retired from Groq's catalog entirely (confirmed via `client.models.list()`, not just one failed
call). This broke every live-LLM code path in the repo (`evaluate.py`, `run_agent.py`,
`benchmark.py`, the Streamlit app), not just this week's new work. Replaced with
`openai/gpt-oss-20b` (currently available on the same key), raising `max_tokens` from 512 to 1024
since it's a reasoning model with real hidden-token overhead (measured: 198 completion tokens for a
trivial triage call, ~126 of them reasoning). Verified end-to-end, not just via an isolated API
call: `triage_graph.invoke()` on a real alert now returns a real verdict via the `llm` path with no
error. Committed separately from the deepteam work (`fix: replace deprecated llama-3.1-8b-instant
with openai/gpt-oss-20b on Groq`), since it's a standalone production fix, not a feature addition.

### Problems / Blockers

- The `llama-3.1-8b-instant` deprecation above was a hard blocker for over an hour of this week —
  couldn't validate anything live until it was root-caused and fixed.
- Branch sequencing note: Week 10's PR (#20) had already been merged to `dev` by the time this
  week's uncommitted follow-up fixes (the `evaluate.py`/`nodes.py`/lit-review corrections mentioned
  under Week 10's "residual gap") were committed — those were moved to their own branch
  (`asma-week-10-followup`) rather than bundled into an already-closed PR. `asma-week-11` is built
  on top of that branch, so its eventual PR shows those commits too unless `asma-week-10-followup`
  merges to `dev` first. **Correction (2026-08-21):** both are already open — PR #21
  (`asma-week-10-followup`) and PR #22 (`asma-week-11`) — not "not yet opened" as originally
  written here; merging #21 first still keeps history atomic, it just isn't blocking anything else
  this week.
- deepteam's README documents an older/simplified `model_callback` API than the installed
  `deepteam==1.0.9` actually exposes, and its `run_all_attacks` parameter defaults to `False`
  (silently sampling one attack per vulnerability instead of the full cross product) — both cost
  real time this week and are documented in `docs/redteam-deepteam-eval.md` so they don't repeat.

### Next steps

- **First:** once Groq's daily quota for `openai/gpt-oss-20b` resets, rerun the focused
  `PromptInjection`/`Roleplay` retry to get the live-verification the quota wall prevented this week
  — this is the actual next step, not a nice-to-have.
- If a more reliable judge model becomes available on this Groq account, retry with it for
  conclusive `PromptInjection`/`Roleplay` results.
- Run `--mode full-graph` (already built into `experiments/deepteam_redteam_eval.py`, not run this
  week) to measure whether the regex/schema guardrails catch what reaches the LLM here.
- Merge `asma-week-10-followup` before or alongside this week's PR to keep history clean.
- GeNIS integration and Wazuh Docker deployment remain open decisions from Week 10, still pending
  supervisor sign-off — not touched this week.

### Continued (2026-08-21): live-verification and full-graph run, both closed out

Two days after the quota exhaustion above, picked up both items flagged as the actual next steps.
Full detail in `docs/redteam-deepteam-eval.md`'s new sections; summary here.

**JSON-repair fix, live-verified — helps, doesn't fully close the gap.** Reran the exact
`PromptInjection`/`Roleplay` retry command with a fresh daily quota (no 429s this time). Result:
4/12 conclusive (up from 0/12 when the quota blocked it), all 4 passed, 0% attack success. Per
attack method, conclusive rate roughly doubled versus the original run (PromptInjection 0/3→1/6,
Roleplay 1/3→3/6). The remaining 8/12 still hit the same generic `"Error enhancing attack"` label —
confirmed real improvement, not a full fix.

**`--mode full-graph`, run for the first time — found a test-harness gap, not the intended
result.** 9/12 conclusive, 0% attack success, which looks like a strong pipeline-level result until
reading the actual per-case output: all 9 conclusive cases routed through `rf_fallback`, not the
LLM. The synthesized full-graph alert (`AlertTitle`, `Category`, `DetectorId` only) never sets
`MitreTechniques`/`SuspicionLevel`/`LastVerdict`, so the Week 6 sparse-context gate
(`route_by_context`, `src/agent/nodes.py:220`) diverts it to the RF baseline before the LLM node is
ever reached — for a routing reason unrelated to the guardrails the run was meant to test. Both
`apply_regex_guardrail` and `apply_schema_guardrail` did pass cleanly on every case, so they aren't
bypassed, they just rarely mattered in this configuration. Real finding, just a different one than
intended: an attack phrased only as `Category` text with no other context gets diverted away from
the LLM by the routing design itself. Fixing `_full_graph_callback()` to set one of the three gating
fields (so the case actually reaches the LLM) is now the first-priority follow-up in
`docs/redteam-deepteam-eval.md`, not attempted this session since it's a test-harness change, not a
pipeline change.

Both new result files committed: `experiments/results/deepteam_redteam_promptinjection_retry.json`
(overwritten with the live-verified version) and
`experiments/results/deepteam_redteam_fullgraph_results.json` (new).

---

## Week 12 — reliability/accuracy audit of the LLM path, full-graph routing fix, lit review

**Branch:** `asma-week-12`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/23 (merged)

Scope driven by supervisor meeting notes rather than the original roadmap slot: (1) fallback/
reliability testing with and without the LLM path; (2) justify or challenge the hybrid design's
accuracy case for using an LLM over RF alone, and try to improve it; (3) whether the LLM reasons
usefully on contextually incomplete alerts; (4) literature context for our evaluation sample sizes.
GeNIS/generalization to a second dataset was explicitly deferred this week (still pending supervisor
sign-off from Week 10, not touched) rather than attempted alongside everything else below.

### PR review follow-ups (asma-week-10-followup / #21, asma-week-11 / #22)

Both open PRs had review comments landed mid-week; addressed before starting new work rather than
alongside it, to keep review threads current.

**PR #21:** the previous "fix" for `evaluate.py`'s silent `predicted_label` default was reviewed and
found inert — the new `raise RuntimeError(...)` sat inside the same `try:` block that wraps
`triage_graph.invoke()`, so the unchanged `except Exception` right below it caught it and still
produced a scored default, just with `predicted=None` instead of `"FalsePositive"` this time. The
check was also over-broad: guardrail-blocked alerts and handled RF/LLM failures legitimately reach
`END` with no `predicted_label` via `human_review_node` (which always sets `needs_human_review`), so
treating every missing-verdict case as fatal would have aborted a run over normal pipeline behavior.
Fixed by moving the check into the `try/except`'s `else` clause (only reached when `invoke()`
didn't raise, so the `except` above can no longer catch it) and narrowing it to fire only when
*both* `predicted_label` and `needs_human_review` are absent — the actual Week 9 dead-end signature.
Legitimate no-verdict outcomes are now tracked separately via `routing_summary.no_verdict_count`.
`tests/test_evaluate.py` grew two cases pinning exactly what the review asked for: a dead-ended
graph must raise and propagate, a guardrail-blocked alert must not. 18/18 passing on that branch.

**PR #22:** review confirmed the deepteam attack types and result numbers check out against the
installed package source, but the PR body's test-plan checklist still said "19/19 passed" after a
second commit added 5 more tests. Corrected to 24/24 (verified via a live `pytest tests/ -v` run,
not just arithmetic) and confirmed via the PR body edit.

### Full-graph red-team routing fix

The first-priority follow-up flagged at the end of Week 11 (`docs/redteam-deepteam-eval.md`):
`_full_graph_callback()`'s synthesized attack alert never set `MitreTechniques`/`SuspicionLevel`/
`LastVerdict`, so `route_by_context()` diverted every one of the 12 test cases to the RF fallback
before the LLM node was ever exercised — the full-graph run was silently testing RF's routing
behavior, not LLM adversarial robustness. Fixed by setting two deliberately neutral placeholder
values (`SuspicionLevel: "Unspecified"`, `LastVerdict: "Unknown"`) on the synthesized alert, chosen
to clear the two-of-three evidence threshold without leaning the verdict either way. Re-ran the
identical scope live: **8 of 12 cases now show `triage_path == "llm"`** (versus 0/12 before), both
guardrails still pass cleanly on every case (confirming they were never actually bypassed, just
rarely the deciding factor for this attack shape), and of the 8 that reached the LLM, 6 completed
and were scored — all 6 resisted the attack (0% attack success on conclusive cases), consistent with
the `llm-only` mode's result. The remaining 6 errors reduce to the same pre-existing judge-model
JSON-reliability issue documented in Week 11, unrelated to this fix. Full detail and the updated
Known Limitations/Future Work lists in `docs/redteam-deepteam-eval.md`; new result file
`experiments/results/deepteam_redteam_fullgraph_llm_reached.json`.

### The LLM-accuracy investigation: two real bugs found, neither explains the gap

Starting point: the paper draft already reported that the hybrid pipeline's LLM-routed subset (209
of 999 alerts, `agent_metrics_week6_fallback_rerun.json`) scores macro F1 0.308 versus the RF-routed
subset's 0.752 — almost the entire hybrid-vs-RF gap traces to the LLM path alone, on the exact
alerts it was designed to handle (the ones with the *most* analyst-readable context). Two candidate
explanations, investigated live rather than assumed:

1. **That run used `llama-3.1-8b-instant`**, retired from Groq's catalog since Week 11 (replaced
   with `openai/gpt-oss-20b`) — a stronger current model might close the gap on its own.
2. **A real formatting bug in `build_context()`** (`src/agent/nodes.py`): `if alert.get(field):`
   treats a missing-data `NaN` float as truthy, so a missing `MitreTechniques`/`SuspicionLevel`
   wasn't omitted — it was rendered as the literal text `"MITRE Technique: nan"` in the LLM's
   prompt. Measured against the exact LLM-eligible subset: **55% of those prompts contained the
   literal string "MITRE Technique: nan"**, 31% contained `"Suspicion Level: nan"`. Fixed with a new
   `_has_value()` NaN-aware presence check (mirrors `fallback_classifier.py`'s `_present()`),
   applied to all six `build_context()` field checks. `tests/test_build_context.py` pins it.

Built `experiments/llm_subset_eval.py`, a new diagnostic scoped to exactly the LLM-eligible subset
(the only alerts either bug could affect), and live-tested both explanations on a stratified
60-alert sample (20/class) of that subset:

| Run | accuracy | macro F1 |
|---|---|---|
| Old run, deprecated model, un-fixed prompt (n=209, reference) | 0.364 | 0.308 |
| Current model, NaN bug fixed, original prompt (n=60) | 0.283 | 0.151 |
| Current model, NaN bug fixed, improved prompt (n=60) | 0.333 | 0.268 |
| RF baseline, same routing subset (n=790, reference) | 0.756 | 0.752 |

**Neither the model swap nor the bug fix closed the gap — if anything, the corrected baseline
scored worse than the old number.** Reading the model's own reasoning text confirms why: it isn't
misparsing a garbled field, it is explicitly reasoning "insufficient evidence → FalsePositive" on
alerts whose only content is a generic category label and a bare suspicion flag — a defensible
inference in isolation that collapsed onto one class 55/60 times. Time-boxed one prompt-engineering
attempt per this week's scope decision: explicit signal-weighting guidance, three grounded few-shot
examples in GUIDE's own field conventions, and reasoning-before-verdict response ordering. This
raised accuracy to 0.333 and macro F1 to 0.268 — a real, measured improvement that eliminated the
single-class collapse — but it remains roughly 40+ macro-F1 points below RF on the same alerts, and
slightly below even the deprecated-model reference number. Read as a genuine, if partial, negative
result: prompt engineering helps, but a few-hundred-token prompt can't reliably supply evidence
GUIDE's schema doesn't encode for these alerts. Reported the full 0.751 → 0.152 → 0.268 progression
in the paper rather than only the improved number.

**Direct answer to "why shift to LLM, is it worth it":** not on raw classification accuracy for this
task — the honest, evidence-based recommendation is the RF baseline alone if macro F1 is the only
criterion. What the LLM path adds instead is qualitative (MITRE-grounded natural-language reasoning
RF cannot produce, and, per the full-graph red-team finding above, different behavior on alerts with
little structured evidence where RF is never exercised). We do not have an analyst-rated evaluation
of that reasoning's usefulness, so the paper reports the accuracy cost precisely rather than
asserting the trade-off is worth it. New paper section `sec:llmgap` ("Where the hybrid gap comes
from, and whether it closes") and a new Discussion opening paragraph make this case directly.

New result files: `experiments/results/llm_subset_eval_baseline.json`,
`experiments/results/llm_subset_eval_improved.json`.

### Literature review: are our sample sizes comparable?

Researched published LLM-based SOC alert-triage evaluations to contextualize the project's 300/999
sample sizes (meeting-note ask, not previously covered in the lit review). Finding: LLM-specific
evaluations in this space are consistently bounded well below their source datasets' full size —
Freitas et al., who introduced GUIDE itself, evaluate their investigation module on 1,000 incidents
out of GUIDE's ~1M, despite classical-ML baselines in the same paper running on regional splits an
order of magnitude larger; other recent papers (Zhao et al.'s information-dense-reasoning work,
retrieval-augmented incident-analysis papers, SIABench) use LLM-evaluation subsamples ranging from 5
to ~20,000 items. Our 300–999 is in line with, and close to, the 1,000-incident scale GUIDE's own
authors used for their comparable LLM/investigation-module evaluation — not full-dataset scale, but
not an outlier either. Added as a new paragraph in the paper's Dataset subsection with two new
citations (`freitas2024guide`, `zhao2025infodense`), not as a standalone lit-review document, since
it's directly load-bearing for the Evaluation section's methodology.

### Full-scale current-model hybrid rerun (999 alerts)

Closed out the "consider re-running" item below same-day rather than leaving it for next week: ran
`python -m src.agent.evaluate --sample-size 999` end to end against the full triage graph (current
model, `build_context()` bug fix applied, original prompt — i.e. exactly what's committed, not the
standalone `llm_subset_eval.py` prompt-engineering variant), output
`experiments/results/agent_metrics_week12_999_current.json`. Same 79.1%/20.9% RF/LLM routing split
as the historical run (790/209 — routing depends only on context-field presence, not the model).
Result: accuracy 0.646, macro F1 0.648 — this replaces the paper's previous 999-alert headline
number (0.669), which was on the now-retired `llama-3.1-8b-instant` model with the formatting bug
present. Splitting this new run by path: RF-routed subset macro F1 0.752 (unaffected by either
fix, as expected), full 209-alert LLM-routed subset macro F1 0.174 / accuracy 0.230 — consistent
with, and slightly worse than, this week's 60-alert diagnostic (0.151), confirming that result
wasn't a small-sample artifact. Groq's daily quota held up fine across all 209 live calls plus
everything else run this week. Paper updated (abstract, `sec:hybrideval`, `sec:llmgap`) to report
this as the primary headline number, with the superseded figure kept as context for why the
model/bug-fix investigation happened in the first place.

### Documentation reconciliation

README's "Current state" summary was still describing end-of-Week-8 status (last touched around PR
#12) despite five weeks of work landing since. Brought current: model swap, Wazuh adapter, red-team
eval, and the paper draft's existence are now all mentioned, and the roadmap table's Aug 30 row
reflects this week's actual scope.

### Problems / Blockers

- None this week that blocked the plan — Groq quota held up across roughly 90 live LLM calls
  (full-graph re-run + two 60-alert diagnostic runs) without hitting the daily wall that blocked
  Week 11's work, and held up again across the 209 live calls in the full-scale rerun above.

### Next steps

- GeNIS integration and Wazuh Docker deployment remain deferred, pending supervisor sign-off (Week
  10/11 status unchanged).
- If further LLM-accuracy work is prioritized, richer context retrieval (e.g. surfacing similar
  historically-labeled alerts, not just MITRE technique text) is a more promising direction than
  further prompt iteration, per this week's finding that prompt engineering alone plateaus well
  below RF's accuracy on this subset.

---

## Week 13 — pre-submission audit of the paper draft, doc hygiene

**Branch:** `asma-week-13`
**PR link:** https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/pull/24 (closed — paper draft moved out of the repo; non-paper content re-landed via PR opened in Week 14)

No new supervisor meeting fell in this slot, so rather than invent new experimental scope (GeNIS
and Wazuh Docker remain explicitly gated on supervisor sign-off, unchanged from Week 10/11/12),
this week did an unbiased, re-derive-don't-trust audit of the IEEE-format paper draft against its
underlying source data, in the same style as Week 10's citation/claims audit.

### Paper audit: one real ~4x error found, plus three smaller issues

Checked every quantitative claim in the paper against its source JSON in `experiments/results/`,
every citation against `docs/literature-review.md`, and internal consistency with
`docs/weekly-progress.md`'s own record of what actually happened. Most of the paper held up exactly
— the 999-alert hybrid numbers (0.646/0.648), the RF baseline (0.751 macro F1), the 300-alert run,
the red-team pass/fail counts, the scalability-benchmark figures, and all cited arXiv
IDs/authors/venues all reproduced exactly against source. Four things didn't:

1. **Real error, not a rounding issue:** the section on the retired ML guardrail claimed the
   real-data benign/injection classifier scores were "mean 0.791 vs. 0.776." The actual measured
   values, confirmed two independent ways (recomputing directly from
   `experiments/results/soc_domain_eval_results.json`'s 40-row scores, and cross-checking Week 8's
   own "Corrected results" table earlier in this file) are **0.209 vs. 0.224** — roughly 4x off.
   The wrong number had also propagated into `README.md`'s "Novel contribution, landed" paragraph.
   The qualitative conclusion (statistically indistinguishable, chance-level 52.5% best accuracy)
   was never wrong — only the two example numbers illustrating it. Fixed in the paper source and
   (via Week 14, see below) in `README.md`.
2. **A citation used to justify this paper's own sample size mischaracterized the cited paper.**
   The Dataset section's sample-size justification described Freitas et al. (GUIDE's own authors)
   as an example of an "LLM-based" evaluation bounded by "per-call inference cost and rate limits."
   Their actual investigation module is Random Forest + PCA + cosine similarity — not an LLM at all
   — and their 1,000-incident cap exists because their evaluation required manual analyst relevance
   judgments per incident, not API cost. Rewrote the paragraph to attribute the cost/rate-limit
   constraint correctly to Zhao et al. and to this project's own evaluation, and the
   manual-judgment constraint to Freitas et al.
3. **Two bibliography entries were defined but never cited:** `guide2024` (the GUIDE dataset itself
   — cited nowhere despite the entire Evaluation section depending on it) and `socaugsurvey2025`
   (Srinivas et al.'s AI-augmented-SOC survey, lit-review Paper 5). Added both at the appropriate
   points.
4. **The current production model was never named in the body text**, only "the current model."
   Named it (`openai/gpt-oss-20b` via Groq) at its first mention.

**Deliberately not touched:** the empty Acknowledgment section — its TODO explicitly defers it to
issue #16's institutional funding decision, not an oversight.

### Paper draft removed from the public repo

Mid-review, the supervisor (Dr. Rana) flagged that the paper draft (`.tex`/`.pdf`) shouldn't be
pushed to the public repository. PR #24 was closed, then the paper files were stripped from
`asma-week-11`/`asma-week-12`/`asma-week-13`'s git history (force-push) and `docs/paper/` was added
to `.gitignore`. The audit findings above (the numeric-error fix, citation corrections) were applied
directly to the paper's own source, which now lives outside this repository; only the parts of the
audit that touch tracked, non-paper files (the `README.md` number, doc hygiene) needed to be
re-landed — done in Week 14 below, since PR #24 itself stayed closed rather than being reopened
against a moving `dev`.

### Problems / Blockers

None on the audit itself. The mid-week paper-draft-in-repo policy correction meant PR #24 couldn't
simply be merged as originally written — see Week 14 for how its non-paper content got re-landed.

---

## Week 14 — land PR #23, re-land Week 13's non-paper fixes, full verification pass

**Branch:** `asma-week-14`
**PR link:** _[fill in when opened]_

No new supervisor meeting fell in this slot either. Rather than invent new experimental scope, this
week closed out two pieces of already-approved, already-correct work that hadn't actually landed
yet, and ran a full verification pass ahead of the Aug 30 writeup checkpoint — the exact situation
Week 13 named as its own precedent.

### What was actually blocking, and why it wasn't obvious

PR #23 (Week 12) had supervisor approval on record, but GitHub still showed it as open. Re-checking
its state directly (rather than trusting the last comment in the thread) showed it was already
`MERGEABLE` / `mergeStateStatus: CLEAN` — the rebase onto `dev` that the approval was waiting on had
already happened on `origin/asma-week-12`, just never merged. Merged it (`gh pr merge 23 --merge`,
preserving the repo's existing merge-commit style used for #20/#21/#22); full test suite re-run
immediately after against the new `dev` tip (32/32 passing) to confirm the merge itself introduced
no regression.

PR #24 (Week 13) stayed closed rather than reopened, since its branch was force-pushed mid-review
and reopening against a `dev` that had since moved (via PR #23) would have re-created the same
conflict problem PR #23 had just been rebased to fix. Re-landing its real, non-paper content as a
fresh PR onto the post-#23 `dev` was cleaner than fighting a stale branch's history.

### Two real risks found and avoided before touching anything

1. **A stale local branch could have resurrected the removed paper draft.** The `asma-week-12`
   branch checked out locally in the main working tree still contained the pre-force-push history
   — including `docs/paper/ieee-conference/draft.tex` and `draft.pdf`, exactly what the supervisor
   had asked removed — and was missing the `evaluate.py` hardening fix entirely. It had never been
   pushed anywhere, but working from it (or accidentally pushing it) would have undone the history
   cleanup. Reset it to match `origin/asma-week-12` before doing anything else, and did all
   subsequent work from fresh `origin/*` refs in an isolated worktree, never from that branch.
2. **Porting Week 13's branch wholesale would have silently reverted PR #21's regression fix.**
   `origin/asma-week-13`'s `src/agent/evaluate.py` and `tests/test_evaluate.py` matched a version of
   the file from *before* PR #21's hardening — missing the `else`-clause `raise` that turns a real
   graph-wiring regression into a loud failure instead of a silently-scored `FalsePositive`, and
   missing the `error_count`/`no_verdict_count` tracking. This isn't mentioned anywhere in Week 13's
   own write-up, so it reads as an artifact of the branch predating that fix rather than intentional
   content. Confirmed by diffing `origin/asma-week-13` against `origin/dev` directly: only
   `evaluate.py`/`test_evaluate.py` regressed; nothing else did. **Only the genuine Week-13 content
   was ported** — the `README.md` number fix, `.gitignore`'s `docs/paper/` exclusion, and the
   Week 10/11/12 PR-link backfill in this file — and `evaluate.py`/`test_evaluate.py` were left
   exactly as `dev` has them post-PR #23. Confirmed after porting: `error_count`, `no_verdict_count`,
   and the graph-wiring-regression `raise` are all still present in `evaluate.py` on this branch.

### The `README.md` number fix, re-verified independently

Recomputed the benign/injection mean scores directly from
`experiments/results/soc_domain_eval_results.json`'s 40 `per_row` entries (not just trusted Week
13's number): benign mean = 0.209 (20 rows, min 0.021, max 0.608), injection mean = 0.224 (20 rows,
min 0.013, max 0.711) — exact match to Week 13's figure and to Week 8's "Corrected results" table
earlier in this file. `README.md`'s "Novel contribution, landed" paragraph updated from the wrong
"0.791 vs 0.776" to the correct "0.209 vs 0.224"; the "Current state" line and PR list updated to
include #23 and to describe the paper draft as living outside the repo rather than pointing at a
path that no longer exists in this tree.

### Verification

- `venv/bin/python -m pytest tests/ -q`: **32/32 passing** against the post-PR-#23 `dev` tip, and
  again **32/32 passing** on this branch after the Week-13 content port — same count both times, no
  regression introduced by either step. (One environment-only failure was hit and resolved before
  these counts: a fresh worktree doesn't carry the gitignored `experiments/results/baseline_model.joblib`,
  which `test_graph_wiring.py`'s RF-fallback test needs; copying it from the main checkout, not a
  code change, fixed it.)
- `README.md`'s ported number independently recomputed from source JSON, not copied on trust (see
  above).
- `gh pr view 23` confirmed `state: MERGED` after merging.

### Still pending — supervisor, not this session

Per PR #23's own "Left for you" list, unchanged and not acted on here since these are explicitly
the supervisor's calls to make, not something to guess at:

- Statements & Declarations for the paper: funding, competing interests, ethics-approval wording,
  the supervisor's own co-authorship (still a `TODO` in the author block), ORCID, and
  data/code-availability/repo-visibility wording for submission.
- GeNIS integration and Wazuh Docker deployment — pending sign-off since Week 10, unchanged.

### Problems / Blockers

None that weren't resolved same-session. The two risks in "Two real risks found and avoided" above
cost investigation time but were caught before anything was pushed, not after.

### Next steps

- Get PR #23's follow-on (this branch) reviewed and merged.
- Supervisor sign-off on the "Still pending" list above, ahead of the Sep 6 "revise draft" and
  Sep 8 final-submission checkpoints.
