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

**Current state:** LangGraph triage agent (Groq/Llama), real GUIDE-dataset evaluation, MITRE ATT&CK RAG, and a regex-based input guardrail (PR #8, currently conflicting — needs a rebase onto `dev`). See issue #10.

**Novel contribution target:** upgrade the guardrail from regex-only to a proper two-stage defense, and quantify what that buys you against paraphrase/obfuscated attacks the regex alone can't see.

| Date | Milestone |
|---|---|
| Aug 2 | Rebase PR #8 onto `dev`, resolve conflicts, get it merged |
| Aug 9 | Implement a second-stage classifier behind the regex fast-path (LlamaFirewall or Prompt Guard — see issue #10) |
| Aug 16 | Re-run the full GUIDE-dataset evaluation with the two-stage guardrail active; measure latency/accuracy tradeoff |
| Aug 23 | Stress-test with paraphrased/obfuscated injection attempts to quantify the improvement over regex-only |
| Aug 30 | Finalize combined scalability + guardrail-effectiveness writeup |
| Sep 6 | Paper/report draft |
| **Sep 8** | **Final submission** |

---

## Supervisor Note

This repository is managed by **CNIT/PNTLab Pisa, TECIP, Scuola Superiore Sant'Anna**.
Please contact your supervisor before making architectural changes.
All code must be original or properly attributed.
Do **not** commit API keys, passwords, or large datasets — see `.gitignore`.
