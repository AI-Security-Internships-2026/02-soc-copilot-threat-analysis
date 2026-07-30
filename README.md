# SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

> **CNIT/PNTLab Pisa · TECIP · Scuola Superiore Sant'Anna — AI Security Internship 2026**

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

| Deliverable | Due |
|---|---|
| Literature review (`docs/literature-review.md`) | Week 2 |
| Architecture design document (`docs/proposal.md`) | Week 3 |
| Working prototype (`src/`) | Week 6 |
| Evaluation results (`experiments/results/`) | Week 7 |
| Final report (`docs/final-report.md`) | Week 8 |

---

## Recommended Technology Stack

```
Python, LangChain, OpenAI API, Elasticsearch, FastAPI, Streamlit
```

See `requirements.txt` for pinned dependencies.

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

## Roadmap to September 8, 2026

**Current state:** LangGraph triage agent (Groq/Llama), real GUIDE-dataset evaluation, MITRE ATT&CK RAG, regex input guardrail, and a two-stage guardrail investigation (PR #12, merged **Jul 30** — a day ahead of schedule). Issue #10 is closed.

**Novel contribution, landed:** built a second-stage ML classifier (TF-IDF+LogReg, selected over LlamaFirewall/Prompt Guard on Ehsanullah's benchmark), then tested it against real GUIDE alert data and found it doesn't transfer — benign and injection scores are statistically indistinguishable on SOC-domain text (0.791 vs 0.776 mean), even though it scores 0.883 F1 on the chat-jailbreak-style set it was benchmarked on. Correctly left ungated rather than deployed broken. This domain-mismatch finding, not the classifier itself, is the actual contribution.

**From here, weekly:**

| Date | Milestone |
|---|---|
| Aug 9 | Time-boxed: try fine-tuning/retraining the classifier on SOC-domain-labeled text (not the chat-style set) to see if the gap closes. If it doesn't pan out quickly, move straight to writeup — this is exploratory, not required |
| Aug 16 | Write up the domain-mismatch finding rigorously alongside the scalability results — cross-domain generalization failure is a legitimate result on its own |
| Aug 23 | Buffer week — address review feedback, polish results and figures |
| Aug 30 | Paper/report draft |
| Sep 6 | Revise draft based on feedback |
| **Sep 8** | **Final submission** |

---

## Supervisor Note

This repository is managed by **CNIT/PNTLab Pisa, TECIP, Scuola Superiore Sant'Anna**.
Please contact your supervisor before making architectural changes.
All code must be original or properly attributed.
Do **not** commit API keys, passwords, or large datasets — see `.gitignore`.
