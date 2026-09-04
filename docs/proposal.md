# Research Proposal: SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Student:** Asma
**Supervisor:** Dr. Rana Abu Bakar, Hafiz Mati Ur Rahman
**Start date:** 1st June 2026
**Expected end date:** September 2026

---

## 1. Background

Design an LLM-powered Security Operations Centre (SOC) co-pilot that automatically triages security alerts, enriches them with threat-intelligence context, and generates plain-language analyst reports.

This project is carried out within the AI Security research agenda of CNIT/PNTLab Pisa (TECIP, Scuola Superiore Sant'Anna).

---

## 2. Problem Statement

SOC analysts face alert volumes that routinely outpace manual triage capacity, and most alerts surfaced by SIEM/XDR tooling turn out to be benign or false positives. Manual triage is slow, inconsistent across analysts, and contributes to alert fatigue — raising the risk that genuine threats get missed or delayed. Existing rule-based and ML classifiers can flag likely true positives but rarely explain their reasoning in a form an analyst can act on quickly, and they don't automatically pull in the broader incident context an analyst would normally gather by hand. This project addresses that gap with an LLM-powered co-pilot that triages alerts, enriches them with relevant context, and produces a plain-language report — keeping a human in the loop for the final disposition rather than fully automating the decision.

---

## 3. Research Questions

1. **RQ1:** How accurately can an LLM-based triage agent classify SOC alerts (true positive / benign positive / false positive) against ground-truth analyst labels, using a real-world dataset such as Microsoft's GUIDE?
2. **RQ2:** Does grounding the LLM's triage decision in structured alert/incident context (via retrieval or multi-agent orchestration) reduce unsupported or hallucinated claims in the generated report, compared to a single-shot LLM call?
3. **RQ3:** What's the trade-off between triage accuracy/report quality and end-to-end latency when a human-in-the-loop review checkpoint is added, and where in the pipeline should it sit?

---

## 4. Proposed Methodology

### 4.1 Data Collection / Dataset

Primary dataset: Microsoft's GUIDE dataset (2024), released as train/test CSVs on Kaggle under a CDLA-2.0 license.

The dataset is built to predict incident triage grades — true positive, benign positive, and false positive — from historical analyst decisions, with 45 features, labels, and unique identifiers across 6.1k organizations and 9.1k unique detector IDs spanning 441 MITRE ATT&CK techniques. Data is structured across three hierarchies — evidence, alerts, and incidents — which maps cleanly onto this project's enrichment pipeline (evidence → alert → incident-level report).

### 4.2 Approach

- Ingest a sample of GUIDE alerts/incidents into Elasticsearch for indexing and retrieval.
- Build a LangGraph-orchestrated agent pipeline:
  1. Alert classifier node (TP/BP/FP)
  2. Context-enrichment node (pulls related evidence/incident records + relevant MITRE technique info)
  3. Report-generation node (plain-language analyst summary)
  4. Human-review checkpoint before final disposition
- Expose the pipeline via a FastAPI backend; Streamlit front-end for the analyst-facing review UI.
- LLM backend: OpenAI API, with agent logic in LangChain/LangGraph.
- Baseline: a classical ML classifier (Random Forest, see `src/models/baseline.py`) trained on the same data, used as the reference point the LLM pipeline is evaluated against for RQ1.

### 4.3 Evaluation Metrics

- Classification accuracy / F1 against GUIDE ground-truth triage grades
- Precision/recall@K on prioritized alert ranking
- End-to-end latency per alert
- Qualitative report quality (reviewed against a rubric)
- Reduction in alerts requiring full manual investigation (proxy for analyst time saved)

### 4.4 Tooling

Python, LangChain, LangGraph, OpenAI API, Elasticsearch, FastAPI, Streamlit, pandas, sklearn (baseline comparison models)

---

## 5. Expected Outcome

A working prototype: an end-to-end alert triage pipeline running on a GUIDE dataset subset, with a Streamlit dashboard showing alert classification, auto-generated analyst report, and human-review/override step — plus an evaluation write-up comparing pipeline decisions against GUIDE ground truth.

---

## 6. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Dataset not publicly available | Medium | Use synthetic data or reach out to CNIT partners |
| Compute resources insufficient | Low | Use university HPC cluster |
| Scope too broad | High | Focus on one sub-problem; extend if time allows |
| GUIDE train CSV is large (~2.4 GB) | Medium | Work with a stratified sample rather than the full dataset for prototyping |

---

_Last updated: 2026-06-19. Status reconciliation appended 2026-08-31 — see below._

---

## Status reconciliation (added 2026-08-31, Week 15)

This proposal is kept as the original planning document rather than edited to match what was built.
Where the two diverge, **the rest of the repository is authoritative** — `docs/final-report.md` for
results, `docs/project-explained.md` for the reasoning, `docs/weekly-progress.md` for the
week-by-week record. This section records the divergences so the proposal is not read as a
description of the current system.

### Answers to the research questions

**RQ1 — accuracy of LLM triage vs. a classical baseline. Answered, in the negative.**
On an identical 209-alert subset — the alerts the router selected as *most* favourable to the LLM —
the Random Forest scored 0.6555 accuracy against the LLM's 0.2823, below the 0.4928 obtained by
always predicting the majority class. Exact McNemar p = 4.66e-12 on 132 discordant pairs. The
comparison is paired, so it is unaffected by the incident-level label leakage separately measured
in this project (39.23% of this subset, against 1.91% exact-row). The system was restructured on that evidence so the classifier assigns every
verdict and the LLM only explains it, which raised whole-pipeline accuracy from 0.6456 to 0.7347 on
an identical 999-alert sample. See `docs/final-report.md` §5.2 and §5.4.

**RQ2 — does grounding reduce unsupported claims? Partially answered, and not as originally
framed.** No controlled grounded-vs-ungrounded comparison of hallucination rates was run. The
closest evidence is Week 14's content analysis: an improved, evidence-citing prompt raised the
proportion of reasoning grounded in specific alert fields from 16.3% to 99.0% and eliminated
generic boilerplate (36.4% → 0.0%), while classification accuracy stayed at 0.282. That separates
groundedness from correctness, which is the finding the final architecture rests on — but it is not
the hallucination measurement this RQ asked for. **Still open**, and now the most important gap,
since the design retains the LLM specifically for explanation quality.

**RQ3 — accuracy/quality vs. latency trade-off for the human-in-the-loop checkpoint, and where it
should sit. Partially answered, and the answer changed.** Latency was measured (RF 0.024–0.060 s
vs. LLM 1.76–2.73 s per alert; RF 45–113× faster). The *placement* question was never studied as a
trade-off — but the checkpoint's basis changed entirely: it gated on the LLM's self-reported
confidence, which Week 15 measured as **inversely calibrated** (0.256 accuracy at "high" vs. 0.383
at "medium"), meaning it auto-accepted the least reliable predictions. It now gates on the Random
Forest's decision margin at 0.20, where accuracy among auto-accepted alerts rises monotonically
with the threshold. See `docs/final-report.md` §5.3.

### Methodology and tooling that changed

| Proposed (§4.2, §4.4) | What was actually built | Why |
|---|---|---|
| Ingest GUIDE into **Elasticsearch** | Never implemented. Alerts are streamed from CSV with a seeded per-class reservoir sampler (`src/agent/evaluate.py`) | An index added no capability the evaluation needed; the sampler is reproducible and cheaper |
| Expose via a **FastAPI** backend | Never implemented. Streamlit only (`src/app.py`) | The deliverable is a research demo, not a service |
| LLM backend: **OpenAI API** | Groq, `openai/gpt-oss-20b` | Moved to Groq in Week 3 for cost/latency; the original Groq model was retired mid-project in Week 11 and replaced |
| LangChain/LangGraph agent logic | LangGraph only | LangChain added no needed abstraction over the graph |

### Evaluation metrics that were never measured (§4.3)

Three of the five proposed metrics have no corresponding result and should not be claimed:

- **Precision/recall@K on prioritised alert ranking** — the system classifies, it does not rank.
  A ranking formulation was never built.
- **Qualitative report quality against a rubric** — no rubric was defined and no rated study was
  run. Automated content analysis (Week 14) is a proxy, not a substitute.
- **Reduction in alerts requiring full manual investigation** — measurable in principle from the
  review-gate escalation rate (19.6% at the current threshold), but never validated against what an
  analyst would actually have escalated, so it is not reported as analyst time saved.

The metrics that *were* measured — accuracy, macro F1 against GUIDE ground truth, and end-to-end
latency — are in `docs/final-report.md` §5.

### Scope items not attempted

GeNIS dataset integration and a live Wazuh Docker deployment both remain pending supervisor
sign-off since Week 10. The Wazuh work that exists is a schema adapter unit-tested against sample
JSON, with an explicitly unvalidated classifier behind it (`docs/wazuh-integration.md`).
