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

_Last updated: 2026-06-19_