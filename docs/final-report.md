# LLM as Explainer, Not Classifier: Measuring the Accuracy Cost of Language-Model Triage on Security Telemetry

**Student:** Asma Imran Chaudhry
**Supervisor:** Dr. Rana Abu Bakar
**Programme:** AI Security Internship 2026
**Date:** September 2026

> Every figure in this report is traceable to a committed file in
> `experiments/results/`. Do not restate a metric here without re-checking it
> against its source JSON. A companion document, `docs/project-explained.md`,
> explains the same material assuming no background knowledge.

---

## Abstract

Security operations centres receive far more alerts than analysts can inspect,
and recent work proposes large language models (LLMs) as automated triage
assistants. We test that proposal on GUIDE, Microsoft's public dataset of 9.5
million real security alerts, and report a negative result with a design
consequence. Comparing an LLM agent against a Random Forest baseline first
required removing a confound common in routed pipelines, including our own:
the two models are scored on different alerts, so a lower LLM score may simply
reflect harder inputs. Scoring both on an identical 209-alert subset — those a
context-based router selected as most favourable to the LLM — the Random Forest
reached 0.6555 accuracy against the LLM's 0.2823, below the 0.4928 obtained by
always predicting the majority class. The Random Forest was correct on 105 of
the 132 alerts where exactly one model was (exact McNemar p = 4.66e-12). The
comparison is paired, so it is unaffected by the incident-level label leakage
we separately measure and quantify in this report (Section 5.10). We further
find the LLM's self-reported confidence is inversely calibrated (0.256 accuracy when reporting "high" versus 0.383 for
"medium"), so a confidence-gated review checkpoint auto-accepted its least
reliable predictions. We restructured the pipeline so the Random Forest assigns
every verdict and the LLM produces only analyst-facing explanations, gating
review on the classifier's decision margin. Whole-pipeline accuracy rose from
0.6456 to 0.7347 on the same 999 alerts, and prompt injection can no longer
alter a triage outcome. **On Microsoft's held-out split the restructured
pipeline reaches 0.6998 accuracy (n=15,000), and that is the figure we lead
with rather than the 0.7347 obtained by sampling the training file.** The
reason is a dataset property we measure here: GUIDE's label attaches to the
incident, not the alert, so a row-level split leaves 55.8% of a train-sampled
evaluation set sharing an incident with training, and on rows the model never
trained on a shared incident is worth 24.3 accuracy points (95% CI
[+0.228, +0.259]). Correcting the baseline's own split rule to be
incident-level costs it 2.8 points (0.7718 → 0.7435). For structured security
telemetry, an LLM is a capable explainer and a poor classifier, and the
distinction is measurable — provided the evaluation split is too.

---

## 1. Introduction

A Security Operations Centre (SOC) receives tens of thousands of alerts per day,
of which the overwhelming majority are not attacks. Analysts must assign each a
disposition — a process called triage — and when volume exceeds capacity, real
intrusions are missed inside the noise. This is alert fatigue, and it is the
most consistently reported operational problem in the SOC literature.

The appeal of applying LLMs is immediate: triage resembles reading and
reasoning, which is what LLMs do. A growing body of work reports encouraging
results. Much of it, however, evaluates on small samples, omits a trivial
baseline, or compares against a different data distribution than the one the
baseline was measured on.

This project built such a system and evaluated it carefully enough to find that
it does not work for this task — and, more usefully, to identify precisely
which part fails and what to do instead.

**Research questions.**

- **RQ1.** Can an LLM agent triage GUIDE alerts more accurately than a
  classical structured-data baseline, measured on identical inputs?
- **RQ2.** Does an LLM's self-reported confidence support a human-review
  checkpoint?
- **RQ3.** What input defences meaningfully protect an LLM-assisted triage
  pipeline against prompt injection?

**Contributions.**

1. A paired comparison of an LLM against a Random Forest on identical alerts,
   with significance testing, removing the routing confound present in our own
   earlier results and in comparable published pipelines (Section 5.2).
2. Evidence that the LLM's self-reported confidence is inversely calibrated,
   inverting the safety property a human-review gate is meant to provide
   (Section 5.3).
3. An architecture — classifier decides, LLM explains — that improves
   whole-pipeline accuracy by 8.9 points on identical data while making prompt
   injection unable to change a triage outcome (Sections 4.3, 5.4).
4. First measurement of the project's live regex guardrail, at 5% recall,
   alongside a deterministic schema check at 100% for the same attack surface
   (Section 5.5).

---

## 2. Related Work

Full annotations are in `docs/literature-review.md`.

Work on LLM-assisted security triage divides into three groups. The first
applies general-purpose LLMs to alert summarisation and disposition, generally
reporting positive results on modest evaluation sets. The second applies
classical supervised learning to structured telemetry; GUIDE's own accompanying
work sits here and establishes that tabular models perform strongly on this data.
The third concerns adversarial robustness of LLM pipelines, including prompt
injection taxonomies and guardrail evaluations.

Our work differs in method rather than subject. Where a routed or hybrid
pipeline is evaluated, the LLM and the classical model are typically measured on
disjoint alert populations selected by the router itself — precisely the
comparison we show is confounded (Section 5.2). We are not aware of prior work
in this setting that scores both models on an identical alert set and reports a
paired significance test. Our contribution is consequently negative and
methodological: the reported advantage of LLM triage on structured telemetry may
in part be an artefact of how such systems are evaluated.

We also depart from the guardrail literature's framing. Rather than pursuing
higher injection-detection recall, we remove the LLM's authority over outcomes,
which converts a detection problem into an architectural invariant (Section 5.5).

---

## 3. Methodology

### 3.1 Dataset

GUIDE (Microsoft, CDLA-2.0): `datasets/GUIDE_train.csv`, 2.4 GB, **9,516,837
alerts**, 45 columns. Class distribution: BenignPositive 43.20%, TruePositive
34.91%, FalsePositive 21.35%, missing 0.54%.

The target, `IncidentGrade`, takes three values. **TruePositive** — real
malicious activity. **BenignPositive** — a real event, correctly detected, not
malicious. **FalsePositive** — the detector misfired and no such event occurred.
The latter two are operationally distinct: one indicates a working detector, the
other a broken one.

Critically, `AlertTitle` and `DetectorId` are **anonymised numeric codes**, not
descriptive text. This bears directly on the results: it removes most of the
natural-language signal an LLM would otherwise exploit.

### 3.2 Evaluation sampling

Accuracy is measured on a **class-balanced sample of 999 alerts** (333 per
class), drawn by a single seeded streaming pass over all 9.5M rows
(`src/agent/evaluate.py`, `numpy.random.default_rng(42)`, per-class reservoir).
Balancing prevents a majority-class predictor from appearing competent; the
corresponding floor is 33.3% and is reported alongside every figure.

### 3.3 Baseline

A Random Forest (200 trees, `random_state=42`) trained on the first 100,000
rows of GUIDE, with identifier columns dropped, timestamps decomposed into
Hour/DayOfWeek/Month, categoricals label-encoded, and an 80/20 stratified split
(`src/models/baseline.py`).

### 3.4 The pipeline

A LangGraph state machine (`src/agent/graph.py`):

```
regex guardrail -> schema guardrail -> MITRE enrichment -> context build
                -> Random Forest verdict -> LLM explanation -> margin gate
```

The LLM is `openai/gpt-oss-20b` served by Groq at `temperature=0`. The
pre-Week-15 hybrid architecture is retained as `build_triage_graph(
"legacy_hybrid")` so prior results remain reproducible.

### 3.5 Metrics

**Macro F1** is the headline: per-class F1 averaged with equal class weight, so
failure on the rarest class (FalsePositive, 21.4%) cannot be masked by the
common ones. Accuracy is reported alongside its **majority-class floor**;
without that floor an accuracy figure is uninterpretable. For paired
model comparisons on identical inputs we use **McNemar's exact test**, which
conditions on discordant pairs and is valid at small counts.

---

## 4. Implementation

### 4.1 Guardrails

`src/agent/guardrails.py` applies four regex families for injection phrasings
and a 4,000-character field cap. `src/agent/schema_guardrail.py` verifies that
`AlertTitle` and `DetectorId` parse as integers — free text in an ID field is
invalid regardless of content. A TF-IDF injection classifier
(`src/agent/ml_guardrail.py`) was evaluated in Week 8, found to perform below
chance, and unwired; it is retained because the negative result is part of the
contribution.

### 4.2 MITRE enrichment

`src/agent/mitre_lookup.py` resolves ATT&CK technique IDs to names and
descriptions from a cached STIX bundle. Two defects were found and fixed in
Week 15. The enrichment node ran *after* context assembly, so the enriched text
never reached the model at all. Separately, the parser split multi-technique
values on `,` while GUIDE uses `;`: of 428 alerts carrying ATT&CK data in the
evaluation sample, 232 used `;` and none used `,`. Resolution rose from **45.8%
to 100%**.

### 4.3 Architecture: classifier decides, LLM explains

`classify_with_rf` is the sole writer of `predicted_label`. `explain_with_llm`
returns only `rationale` and `rationale_status`, never a label or confidence,
and its failure is recorded as an unavailable explanation rather than a triage
error. Human review gates on the Random Forest's **decision margin** (top-1
minus top-2 class probability) at a threshold of 0.20, selected from the sweep
in Section 5.3. `tests/test_graph_wiring.py` asserts the invariant directly.

---

## 5. Results

### 5.1 Baseline

`experiments/results/baseline_metrics.json`, 19,895 held-out alerts:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| BenignPositive | 0.750 | 0.873 | 0.807 | 8,605 |
| FalsePositive | 0.755 | 0.580 | 0.656 | 4,313 |
| TruePositive | 0.814 | 0.766 | 0.789 | 6,977 |
| **Accuracy** | | | **0.7718** | 19,895 |
| **Macro F1** | | | **0.7505** | |

Against a 43.2% majority-class floor. FalsePositive is the weakest class
throughout this work.

### 5.2 RQ1 — The paired comparison

Earlier evaluations routed sparse alerts to the Random Forest and well-evidenced
alerts to the LLM, then compared the resulting scores. Those populations are not
comparable, so a lower LLM score admits the alternative explanation that its
alerts were harder.

`experiments/rf_vs_llm_control.py` scores the Random Forest on the **identical
209 alerts** the LLM was scored on — the subset the router selected as most
favourable to the LLM.

| System | Accuracy | Macro F1 |
|---|---|---|
| **Random Forest** | **0.6555** | **0.6035** |
| **LLM** | **0.2823** | **0.2121** |
| Majority class ("BenignPositive") | 0.4928 | — |
| Uniform random | 0.3333 | — |

Three conclusions follow. The alerts were **not** intrinsically hard: the
Random Forest scored 0.6555 on them, eliminating the confound. The LLM performed
**21 points below a constant answer**. And it identified **none** of the 45
FalsePositive alerts (recall 0.000).

**Significance.** On 132 alerts exactly one model was correct; the Random Forest
was correct on 105. McNemar's exact test: **p = 4.66e-12**.

**Contamination.** Exact-row overlap between this subset and the Random Forest's
training slice is **4/209 (1.91%)**. That figure is correct and it is the wrong
statistic: GUIDE rows are evidence records, several per incident, and
`IncidentGrade` is constant within an incident, so what determines whether the
answer was available in training is whether the *incident* was seen, not
whether the row was. Measured that way, **82/209 (39.23%)** of these alerts
belong to an incident the model saw a labelled row from (Section 5.10).

This does not undermine the comparison in this section, because it is
**paired**: the RF and the LLM are scored on identical alerts, so any
contamination advantage the RF enjoys is present in both columns of the table
and cannot explain a 0.6555-vs-0.2823 split or the McNemar result. It does mean
the RF's *absolute* 0.6555 on this subset is optimistic and should not be read
as a generalisation estimate; Section 5.8's held-out figure is what serves that
purpose.

Week 14 had already shown this is not a prompt-quality artefact: an improved
prompt raised grounded reasoning from 16.3% to 99.0% and TruePositive recall
from 0.07 to 0.54, while accuracy remained at 0.282. The constraint is
structural — with `AlertTitle` reduced to a numeric code, there is little
natural-language signal to exploit.

### 5.3 RQ2 — Confidence is inversely calibrated

The pipeline escalated to a human whenever the LLM's self-reported confidence
was not "high". Measuring that assumption:

| LLM confidence | Alerts | Accuracy |
|---|---|---|
| "high" | 160 | **0.256** |
| "medium" | 47 | **0.383** |
| "low" | 2 | 0.000 |

The signal is **inverted**. The gate auto-accepted 160 predictions at 25.6%
accuracy while escalating 49 at 36.7% — routing the *more* reliable predictions
to humans. A checkpoint intended as a safety property was actively
anti-protective, and nothing in the pipeline's output would have revealed it.

The Random Forest's decision margin, by contrast, is monotone in accuracy:

| Margin threshold | Auto-accepted | Accuracy | Escalation rate |
|---|---|---|---|
| 0.00 | 209 | 0.6555 | 0.0% |
| 0.10 | 187 | 0.6578 | 10.5% |
| **0.20** | **168** | **0.6905** | **19.6%** |
| 0.30 | 135 | 0.7111 | 35.4% |
| 0.50 | 92 | 0.7609 | 56.0% |

We gate at 0.20: accuracy rises 0.6555 → 0.6905 at an escalation rate of roughly
one alert in five. The 0.30 threshold adds 2 points for nearly double the human
workload.

### 5.4 Effect of the architecture change

Whole pipeline, identical 999-alert balanced sample, identical seed:

| Pipeline | Accuracy | Macro F1 |
|---|---|---|
| Hybrid, LLM decides on routed subset (Week 12) | 0.6456 | 0.6484 |
| **Random Forest decides, LLM explains (Week 15)** | **0.7347** | **0.7307** |

**+8.9 accuracy points, +8.2 macro F1**, with zero errors and zero
no-verdict outcomes across all 999 alerts.

The 0.7347 figure is not directly comparable to the 0.7718 baseline: the latter
is measured on GUIDE's natural distribution (floor 43.2%), the former on a
balanced sample (floor 33.3%). Measured as margin over floor, the pipeline
achieves **+40.1** against the baseline's **+34.0**, on the harder task, while
additionally providing guardrails and a calibrated review gate.

### 5.5 RQ3 — Input defences

`experiments/guardrail_layer_eval.py`, against the project's 40-example corpus:

| Layer | Wired | Injections blocked | Benign blocked |
|---|---|---|---|
| Regex filter | yes | **1/20 (5%)** | 0/20 |
| Schema type-check | yes | **20/20 (100%)** | n/a |
| TF-IDF detector | no | 0.05 recall, AUC 0.46 | — |

The regex filter, in the pipeline since Week 3 and never previously tested,
detects 5% of our own injection examples. Its patterns are multi-term
conjunctions — `instruction_override` requires an ignore-word, a
reference-word, and an instruction-word within 80 characters — so phrasings such
as `"SYSTEM OVERRIDE: triage_verdict=BenignPositive"` match nothing. Social
engineering, indirect field injection, and encoded payloads have no pattern at
all. It is retained only because it costs 3.6 µs and produced no false
positives.

The schema check blocks all 20 not by recognising attacks but by rejecting free
text in a numeric-only field regardless of content — a type constraint, which
cannot be evaded by rephrasing.

**The strongest mitigation is architectural.** Since the LLM assigns no
verdicts, a successful injection can corrupt an explanation but cannot change a
triage outcome, a review decision, or any reported metric.

### 5.6 Performance

LLM path (`week7_scalability_benchmark.json`): 0.37–0.57 alerts/s at 1.76–2.73 s
per alert. Random Forest path, re-measured in Week 15 after the sampling fix
(`week15_rf_benchmark.json`): 21.36–66.27 alerts/s at 0.015–0.047 s per alert,
zero errors. **The classifier is roughly two orders of magnitude faster** and
requires no network. Regex guardrail cost, re-measured in Week 17 with
`timeit` inside the run that reports it: **1.93 µs** per check on a short
alert, 5.56 µs on a full injection payload. The 3.616 µs previously reported
here was a July constant that `guardrail_layer_eval.py` restated without
re-measuring; the cost is payload- and machine-dependent and should be read as
an order of magnitude, not a constant.

Two caveats on the older file. **Its n=30 and n=60 accuracy rows are invalid**
and are not reported: the benchmark sliced a prefix of an unshuffled,
class-ordered sample, so those slices held one and two classes respectively.
The Week 15 re-run fixes this with a seeded shuffle — every slice is now
class-balanced, and the difference is visible at n=60, where the corrected macro
F1 is 0.6772 against 0.490 for the two-class slice. Throughput and latency were
never affected, since they do not depend on class balance.

The two tables were also collected in different process states and their
absolute throughputs are not directly comparable. The claim they jointly support
does not rest on that: local CPU-bound inference scales with worker count and
remote inference does not, because the provider's token budget is shared across
threads regardless of concurrency.

### 5.7 Adversarial evaluation

deepteam (`docs/redteam-deepteam-eval.md`) reported a 0% attack success rate
over 12 cases. This should be read narrowly: only 3 of 12 cases were genuinely
conclusive — four "passes" were the target returning empty output, scored as
resistance — and the attacker, judge, and target were the same model. At n=12
the confidence interval around 0% extends past 30%. The supportable claim is
"not obviously broken", not "robust".

### 5.8 Held-out evaluation on `GUIDE_Test.csv`

`experiments/guide_test_holdout_eval.py`. Every figure above is measured on a
sample of `GUIDE_train.csv` — the file the Random Forest trains on — with a
training-row overlap disclosed as small and judged immaterial (1.91%, Section
5.2). Section 5.10 shows that judgement rested on the wrong measurement: the
incident-level overlap on the same samples is 39–56%, and it is worth a
measured 24.3 accuracy points. `GUIDE_Test.csv`, Microsoft's own held-out split (4.1M alerts), had
never been read by any code in this repository before this section.

We drew a fresh, class-balanced sample from `GUIDE_Test.csv` and scored the
existing `baseline_model.joblib` against it without retraining. This section
was first run at n=999 to match the training-side samples elsewhere in this
report; at that scale the held-out-vs-train gap's confidence interval
included zero, so the finding was reported as a close call rather than a
settled effect. To find out whether that was a real "no difference" or just
insufficient statistical power, we re-ran the same evaluation at n=15,000
(5,000/class) — the full `GUIDE_Test.csv` split has 4.1M rows, so this is
still under 0.4% of it — with a matched-scale train-sampled reference
(`experiments/large_train_sampled_rf_eval.py`, RF-only, no live LLM calls
needed) rather than comparing against the smaller n=999 training figure:

| Sample | Accuracy | Macro F1 | n |
|---|---|---|---|
| `GUIDE_train`-sampled, evidence-rich (5.2) | 0.6555 | 0.6035 | 209 |
| `GUIDE_train`-sampled, full pipeline (5.4) | 0.7347 | 0.7307 | 999 |
| `GUIDE_train`-sampled, matched scale | 0.7357 | 0.7331 | 15,000 |
| **`GUIDE_Test.csv`, held-out** | **0.6998** | **0.6949** | 15,000 |

At matched n=15,000 vs n=15,000, the accuracy gap (−0.0359) has a 95%
bootstrap confidence interval of **[−0.0461, −0.0257]** — this **excludes
zero**, so at this sample size the gap is a real, measured generalisation
effect, not sampling noise (macro F1 gap: −0.0383, 95% CI
[−0.0486, −0.0280], also significant;
`experiments/results/holdout_vs_train_symmetric_15000.json`). The smaller
n=999 sample's "not distinguishable from noise" verdict was correct as
stated — it genuinely couldn't distinguish a gap this size from noise at
that n — but it was a power problem, not evidence of no effect. This is the
central methodological point of scaling this evaluation up: the larger,
stricter sample didn't just narrow an existing interval, it changed which
side of significance the finding falls on. Per-class recall shows where the
gap concentrates: FalsePositive recall falls to 0.532 against
BenignPositive's 0.826 and TruePositive's 0.757 at n=999 (per-class recall
at n=15,000 is in the source JSON), so the drop is not uniform across
classes. Unseen-category encoding failure (`transform_with_encoders()` maps
unseen values to −1 rather than crashing) was checked directly and ruled out
as the cause: it fired on only 0.39% of alerts at n=15,000. A 60-alert live
smoke run (at the original n=999 scale) through the full `rf_primary` graph,
including the LLM explanation call, produced zero crashes and predicted
labels that matched the offline prediction on every row — the
explanation-cannot-alter-a-verdict property holds on data the model has
never had any chance to see.

The classifier's one-vs-rest ROC/AUC at n=15,000 is macro 0.8775, 95%
bootstrap CI [0.8731, 0.8817] (per-class: BenignPositive 0.8732,
FalsePositive 0.8555, TruePositive 0.9038) — see
`experiments/results/guide_test_holdout_eval.json`.

### 5.9 The control-node ablation and the effect of incomplete context

`experiments/control_node_ablation.py`. Two questions this report had left as
inference: does the LLM's explanation role genuinely never touch the verdict,
and what happens to accuracy as evidence gets sparser, measured directly
rather than inferred from routing behaviour. First attempted on a reduced
299-alert stratified subsample (bin targets 126/94/50/29) because Groq's
daily token quota was believed, from its rate-limit response headers, to
support only ~300–320 live calls. Re-run this week at the originally-planned
full 999-alert scale, paced across the quota with a `--daily-call-budget`
flag added for exactly this purpose — and, in doing so, discovered the
headers were misleading: Groq's actual constraint is a **200,000 tokens/day
(TPD) limit**, confirmed directly from its own 429 error text
(`"...on tokens per day (TPD): Limit 200000, Used 199789..."`), not the more
generous per-minute figures the response headers advertise. That is the same
underlying limit the original 299-alert design was sized against — this
key does not have a materially larger quota, the visible headers just
described the wrong thing.

| Arm | Mode | n scored / 999 | Accuracy | Macro F1 |
|---|---|---|---|---|
| (a) | `rf_primary`, explanation on | 999 / 999 | **0.7347** | 0.7307 |
| (b) | `rf_primary`, explanation off | 999 / 999 | **0.7347** | 0.7307 |
| (c) | `legacy_hybrid` | 796 / 999 | 0.7550 | 0.7512 |
| (d) | `llm_primary` (LLM decides every alert) | **33 / 999** | 0.3939 | 0.3070 |

**Architecture verification.** Arms (a) and (b) score identically (0.7347)
because the RF decides every verdict in both — explanation on or off cannot
change it. This is a code-level invariant (`explain_with_llm` structurally
cannot write `predicted_label`), already verified by exact row-for-row
matching on a live 299-alert run in the original design; that specific
row-for-row check was not repeated at n=999 because arms (a) and (b) ran in
separate daily invocations and only their aggregate metrics, not per-row
predictions, were retained across that gap (`control_node_ablation.py` now
persists per-row predictions going forward — `experiments/results/
control_node_ablation_rows/` — so a future rerun can repeat the exact check
at full scale). One honest gap: because a verdict comes from the RF
regardless of whether the explanation call itself succeeded, arm (a)'s
`n_scored=999` does not mean 999 explanation calls all succeeded — some
plausibly hit the same daily token cap arms (c) and (d) hit below — but
per-row detail for that specific run was not retained, so the true
explanation-success rate for arm (a) is unverified. It does not affect the
accuracy figures above, which are RF-decided either way.

**What happens when the LLM decides, at genuinely full scale for the
RF-decided bins.** `legacy_hybrid` (arm c) routes by evidence count, RF for
bins 0–1 and LLM for bins 2–3. Bins 0–1 are RF-decided and fully scored at
n=999; bins 2–3 need a live call per alert and mostly did not get one this
run — the daily cap was largely spent by arm (a)'s 999 explanation calls
before arm (c) started:

| Evidence bin | Population | RF (arms a/b) | LLM (`legacy_hybrid`, arm c) |
|---|---|---|---|
| 0 | 453 | 0.7704 | 0.7704 *(RF-decided)* |
| 1 | 337 | 0.7359 | 0.7359 *(RF-decided)* |
| 2 | 180 | 0.6389 | 0.6667 (n=6 scored, 174 unscored) |
| 3 | 29 | 0.7586 | no rows scored |

The evidence-rich bins (2–3) are too data-starved this run to repeat the
Section 5.2-style comparison reliably — 6 scored rows at bin 2, none at bin
3, down from 29 and 13 in the original reduced design (that design ran only
the live arms, without competing against arm (a)'s 999 explanation calls for
the same daily budget). **Sequencing arm (a) before arm (c) and (d) in the
same day was a real design mistake**, not a quota problem alone: running (c)
and (d) first would have preserved more of their evidence-rich-bin budget.

**`llm_primary` (arm d), forced onto every alert, is the arm hit hardest —
worse than the original design, not better.** Of 999 alerts, only 33 scored
(966 hit the same 200k-TPD cap), fewer in absolute count than the original
299-alert design's 42 scored rows. A two-proportion z-test between arm (a)'s
999-scored accuracy and arm (d)'s 33-scored accuracy is still highly
significant (diff 0.3408, 95% CI [0.1718, 0.5097], z=4.31, p=1.6e-5,
`experiments/results/control_node_ablation_two_proportion_tests.json`) — the
effect is large enough to detect even at n=33 — but the interval is
genuinely wide, reflecting that real uncertainty rather than hiding it
behind a misleadingly tight one (an earlier pass of this same file used
n=999, the attempted count, instead of n=33, the actually-scored count, for
this arm — caught and corrected before being reported anywhere further).
The same z-test approach for arm (a) vs. arm (c) (999 vs. 796 scored,
diff −0.0203, 95% CI [−0.0608, 0.0202], p=0.33) shows no significant
difference — expected, since bins 0–1 dominate arm (c)'s scored rows and
those are RF-decided in both arms.

**Data-quality caveat carried forward.** Arm (d)'s calibration table is
still not reported as a finding, for the same reason as before: most
"escalated" rows are unscored alerts, not real low-confidence predictions,
so the number would measure data loss, not calibration.
`control_node_ablation.py` now persists a grouped histogram of every
unscored row's error message before any cleanup (`failure_reasons` in the
committed JSON) — for arm (d) this run, 966/966 unscored rows carry the same
`"...on tokens per day (TPD)..."` message, evidencing the quota-exhaustion
claim in the artifact itself rather than only asserting it in prose.

**Net assessment.** This week's rerun is a genuine improvement for arms (a),
(b), and, on the RF-decided bins, arm (c) — all now fully scored at the
originally-planned n=999, up from n=299. It is not an improvement, and in
one respect (arm d's absolute scored count, and arm c's evidence-rich-bin
coverage) a regression, for the specific question of how the LLM performs
when forced to decide evidence-rich alerts at scale. That question remains
answered best by the original reduced-299 design's `legacy_hybrid` bins
2–3 (n=29, n=13) — cited there, not superseded here — while the RF-vs-LLM
effect size itself (arm a/b/c vs. arm d) is now confirmed, at even smaller
n, to be real and large rather than an artifact of the original small
sample.

---

### 5.10 Incident-level label leakage in GUIDE

`experiments/incident_leakage_audit.py`. Every train-sampled figure in this
report has carried the same disclosure since Week 15: exact-row overlap with
the Random Forest's training slice is ~2%, judged immaterial. This section
shows that measurement was answering the wrong question, and quantifies what
the right one costs.

**The label is a property of the incident, not the alert.** GUIDE rows are
evidence records and several belong to one incident. In the model's own
100,000-row training slice, all **52,797 of 52,797** incidents carry a single
`IncidentGrade` value, and **55.7%** of rows belong to an incident with more
than one row. So one labelled row fixes the label of every sibling.

**`(OrgId, IncidentId)` is a real incident key, not a colliding field.** In a
20,000-row block taken from row 5,000,000 — far from the training slice —
**11,142 of 11,142** rows whose key also appears in the training slice carry
the identical label, against a 43.3% majority-class chance floor. Agreement is
exactly 1.0, so the key identifies a genuine incident and the label is
recoverable from it.

**The evaluation samples are contaminated at the incident level, and the
held-out split is not:**

| Evaluation set | Exact-row overlap | Incident-level overlap |
|---|---|---|
| 999-alert `GUIDE_train`-sampled | 14/999 (1.40%) | **557/999 (55.76%)** |
| 209-alert control subset (5.2) | 4/209 (1.91%) | **82/209 (39.23%)** |
| 999-alert `GUIDE_Test.csv` held-out (5.8) | 0/999 (0%) | **0/999 (0%)** |

**What it is worth: 24.3 accuracy points.** Overlap alone shows the leak
exists, not that it changes anything. To measure that, we drew 300,000 rows
from *past* the training slice — rows the model trained on under no
circumstances — and split them by whether their incident appears in the
training slice. Both buckets were then class-balanced to identical per-class
counts, so the majority-class floor is the same on both sides and cannot
explain a difference. The only thing that varies is whether a labelled sibling
was available:

| Bucket | Accuracy | Macro F1 | n |
|---|---|---|---|
| Incident seen in training ("leaked") | **0.8325** | 0.8312 | 6,000 |
| Incident never seen ("clean") | **0.5893** | 0.5789 | 6,000 |
| **Difference** | **+0.2432** | +0.2523 | 95% CI [+0.2280, +0.2585] |

The interval excludes zero by a wide margin. The advantage also holds *within
every class* — TruePositive +0.4045, FalsePositive +0.2635, BenignPositive
+0.0615 — so no residual class-mix artefact explains it.

**The baseline's own split rule, corrected.** Section 5.1's 0.7718 comes from a
row-level stratified split of the same 100,000-row slice the model trains on;
53.3% of that holdout shares an incident with training.
`experiments/grouped_split_baseline.py` trains the same estimator twice on the
same rows with the same hyperparameters, changing only the split rule:

| Split rule | Accuracy | Macro F1 | Holdout incident leakage | n |
|---|---|---|---|---|
| Row-level (`train_test_split`, deployed) | 0.7718 | 0.7505 | 53.3% | 19,895 |
| Incident-level (`GroupShuffleSplit`) | **0.7435** | **0.7118** | 0.0% | 19,934 |
| **Difference** | **+0.0283** | +0.0388 | | 95% CI [+0.0199, +0.0368] |

The row-level arm reproduces the published 0.7718/0.7505 exactly, which is the
check that this is a faithful re-run and not a differently-configured one. The
difference's CI excludes zero, so the reported baseline is inflated by about
2.8 points, concentrated in FalsePositive (F1 0.656 → 0.587) — the same class
the held-out evaluation found weakest. This is **diagnostic**: the deployed
`baseline_model.joblib` is unchanged, so every pipeline figure in this report
was produced by the same model as before.

**Why 2.8 and not 24.3.** The two numbers answer different questions and it
would overstate the result to conflate them. The 24.3-point gap holds one model
fixed and varies the row population, on class-balanced buckets (majority floor
0.333). The 2.8-point gap varies the split rule, so the grouped model is
*retrained* without those incidents and partly recovers by learning features
that generalise across them; its holdout also follows GUIDE's natural class
distribution (majority floor ≈0.45), so absolute accuracies are not comparable
across the two experiments. "How much signal does a shared incident carry" and
"how inflated is the published baseline" have different answers.

**What this changes.** It supplies the mechanism for Section 5.8's held-out
gap, which that section could measure but not explain: the train-sampled
reference is 55.8% leaked and the held-out sample is 0% leaked, and leakage is
worth 24.3 points on otherwise-comparable rows. It does **not** invalidate
Section 5.2's paired comparison, which scores both models on identical alerts,
so contamination sits in both columns. It does mean every absolute
`GUIDE_train`-sampled accuracy in this report is optimistic, and that the
held-out 0.6998 (Section 5.8) is the only figure here that estimates
generalisation to unseen incidents.

The honest summary is that the project's own disclosure was accurate as an
exact-row measurement and misleading as a contamination claim, and the error
was not conservative.

## 6. Discussion and Limitations

### 6.1 Interpretation

The LLM's failure here is structural, not a tuning problem. GUIDE's anonymised
numeric identifiers remove most natural-language signal, while the Random Forest
learns from 9.5 million labelled rows. Prompt improvement raised explanation
quality substantially and accuracy not at all (Section 5.2), which is the
clearest evidence that the two capabilities are separable — and the basis for
the design conclusion.

The confidence-calibration result generalises beyond this dataset. Any pipeline
gating human review on an LLM's self-reported confidence should verify the
direction of that signal before relying on it. We did not, for several weeks,
and the pipeline was silently auto-accepting its least reliable predictions.

### 6.2 Limitations

1. **The `GUIDE_Test.csv` evaluation (5.8) is a 15,000-alert sample, not the
   full 4.1M-alert file.** At n=999 the measured gap against the train-sampled
   figure had a 95% bootstrap CI including 0 — not distinguishable from noise.
   At n=15,000, matched against an equally large train-sampled reference, the
   same gap's CI ([−0.0461, −0.0257]) excludes 0: a real, if small,
   generalisation effect the smaller sample lacked the power to detect. This
   is itself a limitation worth stating plainly: the n=999 result was not
   wrong, it was underpowered, and nothing about a "not significant" result
   at one sample size rules out a real effect at a larger one. A larger
   held-out run than 15,000 would still sharpen the interval further; a
   single seed's bootstrap remains an improvement over no CI, not a
   substitute for repeated data-collection trials.
2. **Training rows are the first 100,000, not a random sample.** Their class
   distribution matches the global one, which is reassuring but not conclusive.
3. **High-cardinality identifier columns remain features** (`IpAddress`,
   `Sha256`, `AccountName`). These are near-unique per incident and are the
   most likely channel for the leakage measured in Section 5.10; a feature
   ablation isolating their contribution is still outstanding.
4. **`LastVerdict` and `SuspicionLevel` are analyst-derived** and partly
   downstream of the target — target-adjacent leakage. They also drove routing.
5. **The deployed model still uses a row-level split.** Section 5.10 measures
   what that costs (about 2.8 accuracy points against a `GroupShuffleSplit`
   on `(OrgId, IncidentId)`) but the corrected split is diagnostic only: the
   deployed `baseline_model.joblib` was deliberately left unchanged so that
   every pipeline result in this report remains attributable to one model.
   Retraining on an incident-level split, and re-running the pipeline
   evaluations against it, is the natural next step and is not done here.
6. **The leaked-vs-clean comparison is observational, not randomised.**
   Section 5.10 compares rows whose incident was seen in training against rows
   whose incident was not, and those two populations were not assigned at
   random — incidents that recur near the training slice may differ
   systematically from those that do not. Class balancing and the
   within-every-class consistency of the gap rule out the most obvious
   confound, but not every one.
7. **Single runs without confidence intervals.** The 999-alert figures are
   stable to roughly ±3 points; the 209-alert figures to roughly ±6. The paired
   McNemar result does not depend on this.
8. **The injection corpus is 40 self-authored examples**, measuring
   self-consistency rather than generalisation. It bounds how poor the regex
   filter is; it does not estimate production performance.
9. **No live Wazuh deployment.** The adapter is tested against sample JSON only.
10. **The control-node ablation's live arms (5.9) lost most of their data to
   an external API quota, not by design — confirmed to be a hard 200,000
   tokens/day limit on the model, not the more generous per-minute figure
   its response headers advertise.** Re-running at the originally-planned
   full 999-alert scale improved arms (a)/(b) (RF-decided, immune to the
   cap) and arm (c)'s RF-decided bins to genuinely full n=999, but left
   `llm_primary` (arm d) *more* data-starved than the original design — 33
   of 999 scored, versus 42 of 299 before — because running arm (a)'s 999
   explanation calls first consumed most of the day's budget before arms
   (c) and (d) started. The evidence-rich-bin comparison for `legacy_hybrid`
   (arm c) is likewise thinner at full scale (6 scored at bin 2, 0 at bin 3)
   than the original reduced design (29, 13) for the same reason. Section
   5.9's conclusion about the RF-vs-LLM effect size is still supported —
   now by a two-proportion test at n=33 rather than a per-bin breakdown at
   n=29/13 — but the original reduced-299 design's evidence-rich-bin numbers
   remain the better-supported source for that specific breakdown and are
   cited there, not superseded.

---

## 7. Future Work

In priority order: ablate the high-cardinality identifier features to quantify
leakage; adopt incident-level splits; run repeated trials for confidence
intervals, including a larger `GUIDE_Test.csv` run to sharpen the close-call
gap in Section 5.8, and a full-scale rerun of the `llm_primary` control-node
ablation (5.9) once Groq quota allows. Then: fine-tune an LLM on GUIDE to
test whether the structural limit can be overcome; red-team with an independent
judge model at a sample size that can bound an attack success rate; and evaluate
explanation quality directly with analysts, which is the capability this work
argues the LLM should be retained for and the one we have not yet measured.

---

## 8. Conclusion

We built an LLM agent for security alert triage and measured it against a
classical baseline on identical inputs. The language model scored 0.2823
accuracy against the Random Forest's 0.6555 — below the 0.4928 achieved by
always predicting the majority class — on the alerts most favourable to it
(McNemar p = 4.66e-12). Its self-reported confidence was inversely calibrated,
so the human-review checkpoint was auto-accepting its least reliable
predictions. Restructuring the system so the classifier decides and the LLM
explains raised whole-pipeline accuracy from 0.6456 to 0.7347 on identical data
and made prompt injection incapable of altering a triage outcome. For structured
security telemetry, an LLM is a capable explainer and a poor classifier, and the
distinction is measurable.

---

## References

See `docs/literature-review.md` for the annotated set with DOIs, methods,
datasets, and per-paper limitations. The formatted bibliography is maintained
with the journal submission draft, which is held outside this repository at the
supervisor's direction.

---

## Appendix — Result artefacts

| File | Contents |
|---|---|
| `baseline_metrics.json` | Random Forest baseline, 19,895 held-out alerts (row-level split) |
| `grouped_split_baseline.json` | **The same baseline under an incident-level split** |
| `incident_leakage_audit.json` | **Incident-level label leakage and its measured effect** |
| `rf_vs_llm_control.json` | **Paired comparison, calibration, margin sweep, both overlap measures** |
| `agent_metrics_week15_rf_primary.json` | Current pipeline, 999 alerts |
| `guardrail_layer_eval.json` | Per-layer guardrail measurements (cost and AUC now computed) |
| `llm_subset_eval_improved_full209.json` | LLM on the 209-alert subset |
| `soc_domain_eval_results.json` | TF-IDF guardrail negative result |
| `week7_scalability_benchmark.json` | LLM throughput and latency |
| `week15_rf_benchmark.json` | Random Forest throughput |
| `deepteam_redteam_fullgraph_llm_reached.json` | Adversarial evaluation |
| `guide_test_holdout_eval.json` | Held-out `GUIDE_Test.csv` evaluation + RF ROC/AUC |
| `large_train_sampled_rf_eval.json` | Matched-scale train-sampled reference |
| `holdout_vs_train_symmetric_15000.json` | The held-out-vs-train gap and its CI |
| `roc_auc_control_209.json` | RF ROC/AUC on the 209-alert control set |
| `control_node_ablation.json` | Control-node ablation, evidence-count breakdown |
| `control_node_ablation_two_proportion_tests.json` | Significance tests between ablation arms |

Superseded artefacts — including `agent_metrics_week12_999_current.json` (the
"before" side of the architecture change) and `agent_metrics.json` (a
**synthetic-data** run whose labels are random noise) — now live in
`experiments/results/archive/`, with a README recording each file's numbers and
what replaced it.

Reproduction commands are in `docs/demo-runbook.md`; conceptual background is in
`docs/project-explained.md`.
