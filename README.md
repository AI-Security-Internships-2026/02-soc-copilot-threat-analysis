# SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

> **CNIT/PNTLab Pisa · TECIP · Scuola Superiore Sant'Anna — AI Security Internship 2026**

---

## Documentation — start here

| Document | What it is |
|---|---|
| **[`docs/project-explained.md`](docs/project-explained.md)** | **The project explained from zero.** Assumes no background: what SOC triage is, what the three labels mean, what a Random Forest and an LLM each are, every metric defined, the week-by-week story, the limitations, and the questions a reviewer is most likely to ask — with answers. **Read this first.** |
| **[`docs/demo-runbook.md`](docs/demo-runbook.md)** | **The live demo.** Every command in order with its real output, what each one shows, and what to say. About 6 minutes end to end, plus fallbacks if the network or API quota fails. |
| [`docs/final-report.md`](docs/final-report.md) | The full technical report: abstract, method, results, discussion, limitations. Every figure cross-checked against its source JSON. |
| [`docs/weekly-progress.md`](docs/weekly-progress.md) | Week-by-week engineering log, Weeks 1–15. The record of what was done and why. |
| [`docs/literature-review.md`](docs/literature-review.md) | 8 annotated papers with DOIs, methods, datasets, and per-paper limitations. |
| [`docs/proposal.md`](docs/proposal.md) | The original plan, with a status reconciliation recording where the built system diverged from it. |
| [`docs/redteam-deepteam-eval.md`](docs/redteam-deepteam-eval.md) | Adversarial evaluation of the LLM node, its limitations, and what red-teaming means under the current architecture. |
| [`docs/wazuh-integration.md`](docs/wazuh-integration.md) | The Wazuh alert-schema adapter and the unvalidated-classifier caveat that applies to it. |
| [`datasets/README.md`](datasets/README.md) | Dataset provenance, licence, sizes, class distribution, and exactly which split is used. |

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
# see it for yourself (offline, ~10 seconds, no API key needed)
venv/bin/python experiments/rf_vs_llm_control.py
```

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
| Final report (`docs/final-report.md`) | Sep 8 — see "Roadmap to September 8" below; superseded from the original Week 8 date. **Written.** |
| Project explainer (`docs/project-explained.md`) + demo runbook (`docs/demo-runbook.md`) | Week 15 — added for the review meeting |

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

## Roadmap to September 8, 2026

**Current state:** **the Random Forest assigns every verdict; the LLM writes the analyst-facing explanation and cannot influence the outcome** (Week 15). Week 15's control experiment scored both models on the *same* 209 alerts — removing the routing confound that made every earlier comparison unreadable — and found the LLM at 0.2823 accuracy against the RF's 0.6555, below the 0.4928 you get by always answering BenignPositive (exact McNemar p = 4.66e-12), with its self-reported confidence *inversely* calibrated. Restructuring on that evidence moved the full pipeline from 0.6456 to 0.7347 accuracy on the identical 999-alert sample. **On Microsoft's held-out `GUIDE_Test.csv` split the restructured pipeline scores 0.6998 (n=15,000), and that is the figure to quote** — Week 17 measured that GUIDE's label is incident-level, so 55.8% of any train-sampled evaluation set shares an incident with training, and on rows the model never trained on a shared incident is worth 24.3 accuracy points (95% CI [+0.228, +0.259]). See `docs/final-report.md` §5.10. Also current: regex + deterministic schema input guardrails (measured at 5% and 100% injection recall respectively), MITRE ATT&CK enrichment (resolution fixed from 45.8% to 100%), a Wazuh alert-schema adapter, a deepteam red-team evaluation, `docs/final-report.md`, `docs/project-explained.md` (from-zero explainer) and `docs/demo-runbook.md`. The journal paper draft is kept outside this public repo per supervisor guidance — see `.gitignore`.

**Novel contribution, landed:** built a second-stage ML classifier (TF-IDF+LogReg, selected over LlamaFirewall/Prompt Guard on Ehsanullah's benchmark), then tested it against real GUIDE alert data and found it doesn't transfer — benign and injection scores are statistically indistinguishable on SOC-domain text (0.209 vs 0.224 mean), even though it scores 0.883 F1 on the chat-jailbreak-style set it was benchmarked on. Replaced with a deterministic schema/type guardrail instead of gating on the non-transferring classifier. This domain-mismatch finding, not the classifier itself, is the actual contribution.

**From here, weekly:**

| Date | Milestone |
|---|---|
| Aug 9 | Time-boxed: try fine-tuning/retraining the classifier on SOC-domain-labeled text (not the chat-style set) to see if the gap closes. If it doesn't pan out quickly, move straight to writeup — this is exploratory, not required |
| Aug 16 | ~~Write up the domain-mismatch finding~~ — superseded: Week 10 research (Wazuh integration prototype, GeNIS dataset evaluation, literature review finalized) took this slot per supervisor direction. See `docs/weekly-progress.md` Week 10 |
| Aug 23 | Buffer week — address review feedback, polish results and figures; write up the domain-mismatch finding here if not already covered. Partly reallocated: Week 11 used part of this slot for a new, unplanned item — deepteam red-team evaluation of the LLM triage node, prompted by a previously-flagged gap (no adversarial testing had ever reached `classify_with_llm` itself). See `docs/weekly-progress.md` Week 11 and `docs/redteam-deepteam-eval.md` |
| Aug 30 | Paper/report draft — Week 12 folded in reliability/fallback ablations, a fixed full-graph red-team run, an LLM-context prompt bug fix, and a literature-review pass on comparable alert-count benchmarks (`docs/weekly-progress.md` Week 12). Week 13 audited the draft against source data (one real ~4x numeric error found and fixed) and moved the paper source out of this public repo per supervisor guidance. Week 14 landed both: merged PR #23, ported the non-paper Week 13 fixes cleanly onto `dev`. See `docs/weekly-progress.md` Weeks 12–14 |
| Sep 6 | Revise draft based on feedback. Week 15 moved the LLM off the decision path on measured evidence (control experiment, confidence-calibration finding, guardrail measurements) and filled in `docs/final-report.md`; see `docs/weekly-progress.md` Week 15 |
| **Sep 8** | **Final submission** |

---

## Supervisor Note

This repository is managed by **CNIT/PNTLab Pisa, TECIP, Scuola Superiore Sant'Anna**.
Please contact your supervisor before making architectural changes.
All code must be original or properly attributed.
Do **not** commit API keys, passwords, or large datasets — see `.gitignore`.
