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
the 132 alerts where exactly one model was (exact McNemar p = 4.66e-12), with
1.91% training overlap. We further find the LLM's self-reported confidence is
inversely calibrated (0.256 accuracy when reporting "high" versus 0.383 for
"medium"), so a confidence-gated review checkpoint auto-accepted its least
reliable predictions. We restructured the pipeline so the Random Forest assigns
every verdict and the LLM produces only analyst-facing explanations, gating
review on the classifier's decision margin. Whole-pipeline accuracy rose from
0.6456 to 0.7347 on the same 999 alerts, and prompt injection can no longer
alter a triage outcome. Scored instead on Microsoft's held-out test split
rather than a sample of the training file, accuracy is 0.7047 — a small drop
within this report's own noise band. For structured security telemetry, an
LLM is a capable explainer and a poor classifier, and the distinction is
measurable.

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
training slice is **4/209 (1.91%)**, so the result is not memorisation.

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
requires no network. Regex guardrail cost: 3.616 µs per check.

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
small, disclosed, judged-immaterial training-row overlap (1.91%, Section
5.2). `GUIDE_Test.csv`, Microsoft's own held-out split (4.1M alerts), had
never been read by any code in this repository before this section.

We drew a fresh, class-balanced 999-alert sample from `GUIDE_Test.csv` and
scored the existing `baseline_model.joblib` against it without retraining:

| Sample | Accuracy | Macro F1 | n |
|---|---|---|---|
| `GUIDE_train`-sampled, evidence-rich (5.2) | 0.6555 | 0.6035 | 209 |
| `GUIDE_train`-sampled, full pipeline (5.4) | **0.7347** | **0.7307** | 999 |
| **`GUIDE_Test.csv`, held-out** | **0.7047** | **0.7001** | 999 |

The gap (−0.0300) sits right at the edge of the ±3-point noise band this
report already uses for single 999-alert runs — a close call, not a clean
pass. Per-class recall shows where it concentrates: FalsePositive recall
falls to 0.532 against BenignPositive's 0.826 and TruePositive's 0.757, so
the drop is not uniform across classes. Unseen-category encoding failure
(`transform_with_encoders()` maps unseen values to −1 rather than crashing)
was checked directly and ruled out as the cause: it fired on only 0.4% of
alerts. A 60-alert live smoke run through the full `rf_primary` graph,
including the LLM explanation call, produced zero crashes and predicted
labels that matched the offline prediction on every row — the
explanation-cannot-alter-a-verdict property holds on data the model has
never had any chance to see.

The classifier's one-vs-rest ROC/AUC on this sample is macro 0.887
(per-class: BenignPositive 0.882, FalsePositive 0.873, TruePositive 0.905) —
see `experiments/results/guide_test_holdout_eval.json`.

### 5.9 The control-node ablation and the effect of incomplete context

`experiments/control_node_ablation.py`. Two questions this report had left as
inference: does the LLM's explanation role genuinely never touch the verdict,
and what happens to accuracy as evidence gets sparser, measured directly
rather than inferred from routing behaviour. Both are answered on a fresh
299-alert stratified sample (bin targets 126/94/50/29 across 0–3 populated
evidence fields) — reduced from the originally-planned full 999-alert design
after Groq's daily token quota (200,000) turned out to support roughly
300–320 live calls, not the ~2,200 the full design needed.

**Architecture verification.** Running `rf_primary` with the LLM explanation
call on and off across the identical 299 alerts produced **zero mismatched
verdicts or confidences**, both scoring 0.7492 accuracy / 0.7453 macro F1.
This directly confirms, rather than assumes, that `explain_with_llm` cannot
alter a verdict — under live conditions, including real API failures.

**What happens when the LLM decides.** `legacy_hybrid` routes the same 299
alerts by evidence count, RF for bins 0–1 and LLM for bins 2–3:

| Evidence bins | RF | LLM (`legacy_hybrid`) |
|---|---|---|
| 0 (n=126) | 0.7698 | 0.7698 *(RF-decided)* |
| 1 (n=94) | 0.7660 | 0.7660 *(RF-decided)* |
| 2 (n=50, 29 scored) | 0.6600 | **0.3793** |
| 3 (n=29, 13 scored) | 0.7586 | **0.1538** |

The RF holds its accuracy across evidence density; the LLM's collapses from
parity at bins 0–1 to roughly a third to a fifth of the RF's accuracy at the
evidence-rich bins it is specifically routed to decide. This reproduces
Section 5.2's finding through an independent measurement path (live per-bin
routing rather than a reconstructed paired subset).

**Data-quality caveat, disclosed rather than hidden.** The `llm_primary`
arm (LLM decides every alert, unconditionally) lost most of its data to the
same quota exhaustion: only 42 of 299 alerts scored. Reported by bin only
where support exceeds 5 rows — bin 0 (n=25, 0.24), bin 1 (n=9, 0.5556), bin 2
(n=7, 0.00); bin 3 scored a single alert and is not reported. Its calibration
table is not reported as a finding: 257 of 280 "escalated" rows are unscored
alerts, not real low-confidence predictions, so the number would measure
data loss, not calibration. The `legacy_hybrid` comparison above is the
better-supported result for exactly this reason.

---

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

1. **The `GUIDE_Test.csv` evaluation (5.8) is a 999-alert sample, not the
   full 4.1M-alert file.** The measured gap against the train-sampled figure
   (0.7047 vs. 0.7347) sits right at the edge of the ±3-point noise band this
   report uses for single runs at this size — a close call, not a settled
   estimate. A larger held-out run or repeated trials would sharpen it.
2. **Training rows are the first 100,000, not a random sample.** Their class
   distribution matches the global one, which is reassuring but not conclusive.
3. **High-cardinality identifier columns remain features** (`IpAddress`,
   `Sha256`, `AccountName`), which may inflate the baseline.
4. **`LastVerdict` and `SuspicionLevel` are analyst-derived** and partly
   downstream of the target — target-adjacent leakage. They also drove routing.
5. **Splits are row-level, not incident-level**, so alerts from one incident can
   straddle the boundary.
6. **Single runs without confidence intervals.** The 999-alert figures are
   stable to roughly ±3 points; the 209-alert figures to roughly ±6. The paired
   McNemar result does not depend on this.
7. **The injection corpus is 40 self-authored examples**, measuring
   self-consistency rather than generalisation. It bounds how poor the regex
   filter is; it does not estimate production performance.
8. **No live Wazuh deployment.** The adapter is tested against sample JSON only.
9. **The control-node ablation's live arms (5.9) lost most of their data to
   an external API quota, not by design.** `llm_primary` scored only 42 of
   299 alerts; its bin-level breakdown is reported only where support
   exceeds 5 rows, and its calibration table is withheld as a finding since
   its "escalated" bucket is 92% unscored data. The section's conclusion
   rests on the better-supported `legacy_hybrid` comparison (n=29, n=13 at
   the evidence-rich bins) for exactly this reason.

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
| `baseline_metrics.json` | Random Forest baseline, 19,895 held-out alerts |
| `rf_vs_llm_control.json` | **Paired comparison, calibration, margin sweep** |
| `agent_metrics_week15_rf_primary.json` | Current pipeline, 999 alerts |
| `agent_metrics_week12_999_current.json` | Prior hybrid, same 999 alerts |
| `guardrail_layer_eval.json` | Per-layer guardrail measurements |
| `llm_subset_eval_improved_full209.json` | LLM on the 209-alert subset |
| `soc_domain_eval_results.json` | TF-IDF guardrail negative result |
| `week7_scalability_benchmark.json` | Throughput and latency |
| `deepteam_redteam_*.json` | Adversarial evaluation |
| `guide_test_holdout_eval.json` | Held-out `GUIDE_Test.csv` evaluation + RF ROC/AUC |
| `roc_auc_control_209.json` | RF ROC/AUC on the 209-alert control set |
| `control_node_ablation.json` | Control-node ablation, evidence-count breakdown |

Reproduction commands are in `docs/demo-runbook.md`; conceptual background is in
`docs/project-explained.md`.
