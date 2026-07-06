# Literature Review: SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Student:** Asma
**Updated:** 2026-07-03

---

## Paper 1 — Microsoft Security Copilot

| Field | Content |
|---|---|
| **Full title** | Microsoft Security Copilot |
| **Authors** | Microsoft Security Team |
| **Year** | 2024 |
| **Venue** | Industry Tool |
| **URL / DOI** | https://www.microsoft.com/en-us/security/business/ai-machine-learning/microsoft-copilot-for-security |
| **Method** | GPT-4 integrated into SOC workflows for alert summarization, threat hunting, and incident response |
| **Dataset** | Microsoft threat intelligence feeds, customer security data |
| **Key result** | Analysts reported significantly faster triage and reduced alert fatigue |
| **Limitation** | Closed ecosystem, expensive, not adaptable for custom pipelines |
| **Relevance to our project** | Direct industry benchmark — we're building an open, human-in-the-loop equivalent |

**Notes / Quotes:**
> Shows LLMs can meaningfully reduce analyst workload in real SOC environments.

---

## Paper 2 — ADStrike (Agentic AI Red Team Tool)

| Field | Content |
|---|---|
| **Full title** | ADStrike — Agentic AI Penetration Testing Tool via MCP |
| **Authors** | capture0x |
| **Year** | 2025 |
| **Venue** | GitHub / Open Source Tool |
| **URL / DOI** | https://github.com/capture0x/adstrike |
| **Method** | Uses MCP (Model Context Protocol) to give LLM agents access to red team tooling |
| **Dataset** | N/A (active exploitation tool) |
| **Key result** | Demonstrates agentic AI can autonomously execute multi-step attack chains |
| **Limitation** | Red team only — no blue team / defensive counterpart exists |
| **Relevance to our project** | Recommended by supervisor — we are building the blue team equivalent with human-in-the-loop |

**Notes / Quotes:**
> Our project is essentially: ADStrike for red team, SOC Copilot for blue team.

---

## Paper 3 — LLM-Based SIEM Alert Triage

| Field | Content |
|---|---|
| **Full title** | Automated Cyber Threat Intelligence: LLMs for SIEM Alert Triage |
| **Authors** | Ferrag et al. |
| **Year** | 2024 |
| **Venue** | arXiv |
| **URL / DOI** | https://arxiv.org/abs/2407.08628 |
| **Method** | Fine-tuned and prompted LLMs to classify and prioritize SIEM alerts |
| **Dataset** | CICIDS2017, synthetic SIEM logs |
| **Key result** | LLMs outperformed rule-based systems on alert classification accuracy |
| **Limitation** | Tested on synthetic data; real SOC environments are noisier |
| **Relevance to our project** | Core task overlap — alert triage is exactly what our copilot needs to do |

**Notes / Quotes:**
> Confirms LLMs are viable for structured alert classification tasks.

---

## Paper 4 — CORTEX (Collaborative Multi-Agent Alert Triage)

| Field | Content |
|---|---|
| **Full title** | CORTEX: Collaborative LLM Agents for High-Stakes Alert Triage |
| **Authors** | Wei, Tay, Liu, Pan, Luo, Zhu, Jordan |
| **Year** | 2025 |
| **Venue** | arXiv |
| **URL / DOI** | https://arxiv.org/abs/2510.00311 |
| **Method** | Multi-agent (divide-and-conquer) LLM architecture for triage — agents ground decisions in tool-fetched evidence instead of one model doing end-to-end interpretation, retrieval, and adjudication |
| **Dataset** | Custom fine-grained SOC workflow dataset — process-level triage traces across 10+ real scenarios |
| **Key result** | Large reductions in false positives and improved reasoning quality/auditability vs. single-agent baselines |
| **Limitation** | Multi-agent coordination adds inference cost and complexity; evaluated on custom traces, not a standardized public benchmark |
| **Relevance to our project** | Closest published architecture to ours — directly informs our human-in-the-loop, evidence-grounded triage design |

**Notes / Quotes:**
> Validates a multi-agent, evidence-grounded approach over a single do-everything LLM for high-stakes triage.

---

## Paper 5 — AI-Augmented SOC Survey

| Field | Content |
|---|---|
| **Full title** | AI-Augmented SOC: A Survey of LLMs and Agents for Security Automation |
| **Authors** | Srinivas, Kirk, Zendejas, Espino, Boskovich, Bari, Dajani, Alzahrani |
| **Year** | 2025 |
| **Venue** | Informatics (MDPI), Vol. 5, No. 4, Article 95 |
| **URL / DOI** | https://www.mdpi.com/2624-800x/5/4/95 |
| **Method** | Systematic literature survey of LLM/agent applications across SOC tasks (log summarization, alert triage, threat intel, incident response, report generation, asset discovery, vulnerability management) |
| **Dataset** | N/A (survey paper) |
| **Key result** | Maps the current SOC-automation landscape; finds human-AI collaboration outperforms full automation as the dominant successful pattern |
| **Limitation** | Survey-level synthesis — no novel empirical evaluation of its own |
| **Relevance to our project** | Gives us a taxonomy to position our copilot in the literature and justifies our human-in-the-loop design choice |

**Notes / Quotes:**
> Confirms human-AI collaboration, not full automation, is where the field is converging — supports our project's core design assumption.

---

## Reference Table (Quick Overview)

| # | Title (short) | Authors | Year | Method | Dataset | Relevance |
|---|---|---|---|---|---|---|
| 1 | Microsoft Security Copilot | Microsoft | 2024 | GPT-4 in SOC workflows | Internal threat intel | Industry benchmark |
| 2 | ADStrike | capture0x | 2025 | Agentic AI via MCP | N/A | Blue team counterpart |
| 3 | LLM SIEM Alert Triage | Ferrag et al. | 2024 | Fine-tuned LLMs | CICIDS2017 | Core task overlap |
| 4 | CORTEX | Wei et al. | 2025 | Multi-agent LLM triage | Custom SOC traces | Closest architecture match |
| 5 | AI-Augmented SOC Survey | Srinivas et al. | 2025 | Literature survey | N/A | Positions project in field |

---

## Tools and Datasets Identified

| Name | Type | URL | Notes |
|---|---|---|---|
| GUIDE | Dataset | https://www.kaggle.com/datasets/Microsoft/microsoft-security-incident-prediction | Largest public real-world SOC alert/incident dataset — 1.6M alerts, 1M analyst-triaged incidents from 6,100+ orgs, released 2024 (CDLA-2.0). Replaces CICIDS2017, which is outdated network-flow data not designed for SOC/LLM triage. |
| ADStrike | Tool | https://github.com/capture0x/adstrike | Agentic red team tool, MCP-based |
| Microsoft Security Copilot | Tool | https://www.microsoft.com/en-us/security/business/ai-machine-learning/microsoft-copilot-for-security | Industry SOC copilot benchmark |