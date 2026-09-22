# SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

> **CNIT/PNTLab Pisa · TECIP · Scuola Superiore Sant'Anna — AI Security Internship 2026**

---

## Documentation — start here

| Document | What it is |
|---|---|
| **[`docs/project-explained.md`](docs/project-explained.md)** | **The project explained from zero.** Assumes no background: what SOC triage is, what the three labels mean, what a Random Forest and an LLM each are, every metric defined, the week-by-week story, the limitations, and the questions a reviewer is most likely to ask — with answers. **Read this first.** |
| **[`docs/demo-runbook.md`](docs/demo-runbook.md)** | **The live demo.** Every command in order with its real output, what each one shows, and what to say. About 6 minutes end to end, plus fallbacks if the network or API quota fails. |
| [`docs/final-report.md`](docs/final-report.md) | The full technical report: abstract, method, results, discussion, limitations. Every figure cross-checked against its source JSON. |
| [`docs/weekly-progress.md`](docs/weekly-progress.md) | Week-by-week engineering log, Weeks 1–17. The record of what was done and why. |
| [`docs/literature-review.md`](docs/literature-review.md) | 8 annotated papers with DOIs, methods, datasets, and per-paper limitations. |
| [`docs/proposal.md`](docs/proposal.md) | The original plan, with a status reconciliation recording where the built system diverged from it. |
| [`docs/redteam-deepteam-eval.md`](docs/redteam-deepteam-eval.md) | Adversarial evaluation of the LLM node, its limitations, and what red-teaming means under the current architecture. |
| [`docs/wazuh-integration.md`](docs/wazuh-integration.md) | The Wazuh alert-schema adapter and the unvalidated-classifier caveat that applies to it. |
| [`datasets/README.md`](datasets/README.md) | Dataset provenance, licence, sizes, class distribution, exactly which split is used, and how to verify your copy's integrity. |
| [`docs/stale_claims_audit.md`](docs/stale_claims_audit.md) | Every occurrence of a superseded figure, classified and resolved (issue #30 Part A). |
| [`docs/field-inclusion-memo.md`](docs/field-inclusion-memo.md) | Whether the target-adjacent features leak, measured rather than assumed (issue #30 Part C). |
| [`docs/soc-injection-benchmark-datasheet.md`](docs/soc-injection-benchmark-datasheet.md) | Datasheet for the 500-row SOC prompt-injection benchmark: composition, collection, annotation status, licence, known biases (issue #35/#37). |
| [`docs/m3-2-detector-family-matrix.md`](docs/m3-2-detector-family-matrix.md) | 8-detector × 7-family failure analysis against that benchmark, with a real cited miss per cell (issue #36). |
| [`docs/reproduce_from_scratch.log`](docs/reproduce_from_scratch.log) | A clean-room run of all four baselines from a fresh virtualenv (issue #29). |

The journal paper draft is deliberately **not** in this repository, per supervisor guidance.

### Headline result

On an identical 209-alert subset — the alerts the router selected as *most* favourable to the LLM —
the Random Forest scored **0.6555** accuracy against the LLM's **0.2823**, below the **0.4928**
obtained by always answering `BenignPositive` (exact McNemar p = 4.66e-12). The LLM's self-reported
confidence was *inversely* calibrated. The pipeline was restructured so the classifier assigns every
verdict and the LLM only explains it, taking whole-pipeline accuracy from **0.6456 to 0.7347** on the
same 999 alerts — and **0.6998 on Microsoft's held-out split** (n=15,000), which is the figure to
quote, because GUIDE's label is incident-level and 55.8% of any train-sampled evaluation set shares
an incident with training. Details in [`docs/final-report.md`](docs/final-report.md) §5.2–5.4 and
§5.10.

```bash
# see it for yourself (offline, ~10 seconds, no API key, no network)
venv/bin/python experiments/rf_vs_llm_control.py
```

It reads two committed files — the 999-alert evaluation cache and the LLM's
recorded per-alert answers — plus the trained classifier. The classifier
(`experiments/results/baseline_model.joblib`, 590 MB) is too large to commit;
build it once with `venv/bin/python -m src.models.baseline`, which needs
`datasets/GUIDE_train.csv` (see [`datasets/README.md`](datasets/README.md)).
Without `GUIDE_train.csv` the script still prints every headline figure and
skips only the training-overlap diagnostic, which it says out loud.

### What the classifier leaves on the table

The deployed classifier is trained on 100,000 of `GUIDE_train.csv`'s **9,516,838** rows. Week 17
measured what the rest is worth, scoring every candidate on the same 0%-leaked held-out split with
incident-level splits throughout: the best configuration (RF-200, `min_samples_leaf=5`,
`class_weight="balanced"`, 1M rows) reaches **0.7355 accuracy / 0.7338 macro F1 against the deployed
0.6998 / 0.6949**, and lifts `FalsePositive` recall from 0.514 to 0.607. Data volume beats model
sophistication: at a matched 500k rows, plain Random Forest beats gradient boosting.

The same study closes the identifier feature-inflation ablation carried from Week 15, with a
negative result — removing the twelve identifier-like features that survive the ID filter costs
0.0411 accuracy on a leaky row-level split but **0.0440 on the clean held-out split**, the opposite
of the ordering memorisation would produce, so those features carry generalisable signal.

**The deployed model is deliberately unchanged** — adopting a new classifier would move every
published number days before submission. See `experiments/results/classifier_improvement_study.json`
and `docs/weekly-progress.md` Week 17.

```bash
venv/bin/python experiments/classifier_improvement_study.py --max-rows-cap 500000
```

### M3 guardrail benchmark — quick start

`datasets/soc_injection_benchmark_v1.csv` (500 rows: 400 template-generated attacks across 7
families + 100 real GUIDE `BenignPositive` alerts) replaces the earlier 40-example injection corpus
for detector evaluation. At this scale, the previously-reported TF-IDF detector's 0.46 ROC-AUC
(measured on the 40-row set) drops to **0.1978** — confirming negative transfer, not a fluke of a
small sample. The union of the three heuristic layers (regex, schema, and a new SOC-aware field
allowlist) catches **96.75%** of attacks at **0%** false positives on the 100 real-alert controls,
outperforming every learned detector tested. One dispatcher reproduces every detector's score
against it:

```bash
venv/bin/python scripts/benchmark_soc_injection.py --detector all
```

Offline detectors (L1, H1, H2, H3, H-union) run immediately. L2/L3 make live, quota-metered Groq
calls and checkpoint their progress, so a run can be resumed across invocations
(`--daily-call-budget N` to pace one). See [`docs/soc-injection-benchmark-datasheet.md`](docs/soc-injection-benchmark-datasheet.md)
and [`docs/m3-2-detector-family-matrix.md`](docs/m3-2-detector-family-matrix.md) for the results.

---

## Research Problem

Design an LLM-powered Security Operations Centre (SOC) co-pilot that automatically triages security alerts, enriches them with threat-intelligence context, and generates plain-language analyst reports.

---

## Objectives

1. Conduct a systematic literature review on the topic.
2. Design and implement a proof-of-concept prototype.
3. Evaluate the prototype on real or benchmark datasets.
4. Document findings in a final technical report.
5. Present results to the research group.

---

## Expected Deliverables

| Deliverable | Due | Status |
|---|---|---|
| Literature review (`docs/literature-review.md`) | Week 2 | **Done** — 8 annotated papers with DOIs |
| Architecture design document (`docs/proposal.md`) | Week 3 | **Done** — with a status reconciliation of where the build diverged |
| Working prototype (`src/`) | Week 6 | **Done** — LangGraph pipeline, 118 passing tests |
| Evaluation results (`experiments/results/`) | Week 7 | **Done** — 20 committed artifacts, each with a producing script |
| Final report (`docs/final-report.md`) | Sep 8 (superseded from Week 8) | **Done** — every figure cross-checked against its source JSON |
| Journal manuscript (Elsevier *Computers & Security*, 22pp) | Sep 20 — issue #47 | **In progress** — kept outside this repo per supervisor guidance |
| Project explainer (`docs/project-explained.md`) + demo runbook (`docs/demo-runbook.md`) | Week 15 — added for the review meeting | **Done** |
| Held-out evaluation + leakage audit (`experiments/guide_test_holdout_eval.py`, `incident_leakage_audit.py`, `grouped_split_baseline.py`) | Weeks 16–17 — unplanned, see roadmap | **Done** — produced the headline result |
| Presentation to the research group | Sep 8 | **Pending** — runs off `docs/demo-runbook.md` |

---

## Recommended Technology Stack

*Originally proposed:*

```
Python, LangChain, OpenAI API, Elasticsearch, FastAPI, Streamlit
```

*Actually built:*

```
Python, LangGraph, Groq (openai/gpt-oss-20b), scikit-learn, pandas, Streamlit, deepteam
```

Elasticsearch and FastAPI were never implemented, and the OpenAI backend was replaced by Groq in
Week 3. See the status reconciliation in [`docs/proposal.md`](docs/proposal.md) for why. See
`requirements.txt` for pinned dependencies.

---

## Weekly Workflow

```
Monday     – Review weekly tasks in tasks/week-XX.md
Tue–Thu    – Implementation / experiments
Friday     – Document progress in docs/weekly-progress.md
Friday     – Open weekly Pull Request from your branch → dev
```

---

## Branching Policy

| Branch | Purpose |
|---|---|
| `main` | Stable, supervisor-reviewed code only |
| `dev` | Integration branch — merge weekly PRs here |
| `<your-name>-week-XX` | Your working branch for each week |

**Students must never push directly to `main`.**

---

## Pull Request Policy

- One PR per week, targeting the `dev` branch.
- PR title format: `[Week XX] Brief description`
- PR description must reference the weekly task file and summarise what was done.
- A supervisor or co-student must review before merging.

---

## Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis.git
cd 02-soc-copilot-threat-analysis

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your weekly branch
git checkout dev
git pull origin dev
git checkout -b your-name-week-01

# 5. Run the starter script
python src/main.py
```

---

## Roadmap to September 20, 2026

**Current state (Week 17):** the Random Forest assigns every verdict; the LLM writes the
analyst-facing explanation and cannot influence the outcome. Verified end to end at n=999 —
`experiments/verdict_invariance_check.py` runs the whole deployed graph and finds every verdict
identical to the classifier's own prediction, with the three wiring assertions in
`tests/test_graph_wiring.py` covering the structural claim.

Also current: regex + deterministic schema input guardrails (5% and 100% injection recall
respectively — the regex layer is weak and reported as such), MITRE ATT&CK enrichment (resolution
fixed from 45.8% to 100%), a Wazuh alert-schema adapter, and a deepteam red-team evaluation of the
full graph (0/12 attacks succeeded, 6 of 12 errored). The journal paper draft is kept outside this
public repo per supervisor guidance — see `.gitignore`.

The headline figures are in "Headline result" above; they are not repeated here.

**Contributions, in the order they matter:**

1. **Incident-level label leakage in GUIDE, measured.** The dataset's label is a property of the
   incident, not the alert row, and it is constant within an incident (11,141 of 11,141 colliding
   rows agree). So the row-level split that this project — and the published baselines it compares
   against — used lets sibling rows of one incident fall on both sides. It is worth **24.3 accuracy
   points**. This is the finding with consequences outside this repository.
2. **A paired measurement of what the LLM costs as a classifier.** On an identical 209-alert subset
   chosen to favour it, the LLM scored below a constant answer, and its self-reported confidence was
   *inversely* calibrated — so the human-review gate was auto-accepting its worst predictions.
3. **An architecture that acts on (2):** the classifier decides, the LLM explains, and a prompt
   injection therefore cannot change a triage outcome — verified at n=999, not asserted.
4. **A negative result on model-based input guardrails.** A TF-IDF+LogReg classifier scoring 0.883
   F1 on a chat-jailbreak benchmark does not transfer to SOC text at all: benign and injection
   scores are statistically indistinguishable (0.209 vs 0.224 mean, AUC 0.46). It was rejected
   rather than deployed, and replaced with a deterministic schema guardrail. The *domain-mismatch
   finding*, not the classifier, was the useful output.

**From here, weekly:**

| Date | Milestone |
|---|---|
| Aug 9 | ~~Time-boxed: try fine-tuning/retraining the classifier on SOC-domain-labeled text~~ — **not done, deliberately.** Week 9 had already found the root cause (the guardrail classifier does not transfer to SOC text at all: benign and injection scores are statistically indistinguishable), which makes retraining on a slightly different set the wrong response. The slot went to shipping the deterministic schema guardrail instead. Recorded at `docs/weekly-progress.md` Week 9, "Reframing the Aug 9 milestone" |
| Aug 16 | ~~Write up the domain-mismatch finding~~ — superseded: Week 10 research (Wazuh integration prototype, GeNIS dataset evaluation, literature review finalized) took this slot per supervisor direction. See `docs/weekly-progress.md` Week 10 |
| Aug 23 | Buffer week — address review feedback, polish results and figures; write up the domain-mismatch finding here if not already covered. Partly reallocated: Week 11 used part of this slot for a new, unplanned item — deepteam red-team evaluation of the LLM triage node, prompted by a previously-flagged gap (no adversarial testing had ever reached `classify_with_llm` itself). See `docs/weekly-progress.md` Week 11 and `docs/redteam-deepteam-eval.md` |
| Aug 30 | Paper/report draft — Week 12 folded in reliability/fallback ablations, a fixed full-graph red-team run, an LLM-context prompt bug fix, and a literature-review pass on comparable alert-count benchmarks (`docs/weekly-progress.md` Week 12). Week 13 audited the draft against source data (one real ~4x numeric error found and fixed) and moved the paper source out of this public repo per supervisor guidance. Week 14 landed both: merged PR #23, ported the non-paper Week 13 fixes cleanly onto `dev`. See `docs/weekly-progress.md` Weeks 12–14 |
| Aug 30 (cont.) | Week 15 moved the LLM off the decision path on measured evidence — the control experiment, the confidence-calibration finding, the guardrail measurements — and filled in `docs/final-report.md`. See `docs/weekly-progress.md` Week 15 |
| Sep 3 | **Week 16, unplanned:** every point estimate in the project gained a bootstrap confidence interval and a significance test (`experiments/stats_utils.py`), and `GUIDE_Test.csv` — Microsoft's own held-out split, untouched until then — was evaluated for the first time at n=15,000. That run produced the **0.6998** headline. See `docs/weekly-progress.md` Week 16 |
| Sep 6 | **Week 17, unplanned:** a verification pass that found the reason the held-out number is lower. GUIDE's label is incident-level, so a row-level split leaks sibling rows: **55.8%** of any train-sampled evaluation set shares an incident with training, and that is worth **24.3 accuracy points** (95% CI [+0.228, +0.259]). Also landed the grouped-split baseline, the classifier-headroom study, a single shared probability tie-break, and the reproducibility fixes in this README. See `docs/weekly-progress.md` Week 17 |
| **Sep 8** | **M1 — Repo Stabilization** (issues [#29](https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/issues/29), [#30](https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis/issues/30)): clean-room reproducibility audit; stale-claims audit, HITL-gate calibration, DetectorId/feature-inclusion audit, dataset integrity manifest |
| Sep 10 | M2 — Classifiers/Leakage (#31–#34) |
| Sep 12 | M3 — Guardrails/Benchmark (#35–#37) |
| Sep 15 | M4 — Integrity/Explanation (#38–#41) |
| Sep 17 | M5 — Ablations/Cost (#42, #43) |
| **Sep 20** | **M6 — Manuscript/Submission** (#44–#47): Elsevier *Computers & Security*, 22 pages, 12 sections; IEEE IoT Journal as the alternate |

**The submission date moved.** Every document in this repository said Sep 8 until
2026-09-06, when the supervisor filed issues #29–#47 restructuring the remaining
work into six milestones. Sep 8 is now **M1 only**; submission is **Sep 20**, and
the venue changed from the IEEE conference format to a full-length Elsevier
*Computers & Security* manuscript. Work the issues in number order.

---

## Supervisor Note

This repository is managed by **CNIT/PNTLab Pisa, TECIP, Scuola Superiore Sant'Anna**.
Please contact your supervisor before making architectural changes.
All code must be original or properly attributed.
Do **not** commit API keys, passwords, or large datasets — see `.gitignore`.
