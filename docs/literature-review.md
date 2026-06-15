# Literature Review: SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Student:** Asma
**Updated:** 2026-06-15

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

## Reference Table (Quick Overview)

| # | Title (short) | Authors | Year | Method | Dataset | Relevance |
|---|---|---|---|---|---|---|
| 1 | Microsoft Security Copilot | Microsoft | 2024 | GPT-4 in SOC workflows | Internal threat intel | Industry benchmark |
| 2 | ADStrike | capture0x | 2025 | Agentic AI via MCP | N/A | Blue team counterpart |
| 3 | LLM SIEM Alert Triage | Ferrag et al. | 2024 | Fine-tuned LLMs | CICIDS2017 | Core task overlap |

---

## Tools and Datasets Identified

| Name | Type | URL | Notes |
|---|---|---|---|
| CICIDS2017 | Dataset | https://www.unb.ca/cic/datasets/ids-2017.html | Widely used IDS benchmark dataset |
| ADStrike | Tool | https://github.com/capture0x/adstrike | Agentic red team tool, MCP-based |
| Microsoft Security Copilot | Tool | https://www.microsoft.com/en-us/security/business/ai-machine-learning/microsoft-copilot-for-security | Industry SOC copilot benchmark |