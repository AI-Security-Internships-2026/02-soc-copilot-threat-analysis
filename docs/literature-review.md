# Literature Review: SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage

**Student:** Asma
**Updated:** 2026-08-14

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
| **Full title** | ADStrike — AI-Powered Modular Active Directory Red-Team Framework via MCP |
| **Authors** | capture0x |
| **Year** | 2025 |
| **Venue** | GitHub / Open Source Tool |
| **URL / DOI** | https://github.com/capture0x/AdStrike |
| **Method** | MCP server (53 tools) giving LLM agents access to Active Directory red-team tooling — AD enumeration, Kerberos/ADCS attacks, DCSync, etc. |
| **Dataset** | N/A (active exploitation tool) |
| **Key result** | Demonstrates agentic AI can autonomously execute multi-step AD attack chains |
| **Limitation** | Red team only, and scoped specifically to Active Directory — no blue team / defensive counterpart exists |
| **Relevance to our project** | Recommended by supervisor — we are building the blue team equivalent with human-in-the-loop |

**Notes / Quotes:**
> Our project is essentially: ADStrike for red team, SOC Copilot for blue team.

---

## Paper 3 — Generative AI in Cybersecurity

| Field | Content |
|---|---|
| **Full title** | Generative AI in Cybersecurity: A Comprehensive Review of LLM Applications and Vulnerabilities |
| **Authors** | Ferrag, Alwahedi, Battah, Cherif, Mechri, Tihanyi, Bisztray, Debbah |
| **Year** | 2024 (rev. Jan 2025) |
| **Venue** | arXiv |
| **URL / DOI** | https://arxiv.org/abs/2405.12750 |
| **Method** | Comprehensive review of LLM applications across cybersecurity domains (intrusion detection, cyber threat intelligence, malware/phishing detection, software/hardware security); benchmarks 42 LLMs on cybersecurity knowledge and hardware security |
| **Dataset** | N/A (review paper; surveys results across many underlying benchmarks) |
| **Key result** | Maps where LLMs already help across the cybersecurity lifecycle, and separately catalogs LLM-specific vulnerabilities (prompt injection, insecure output handling, data poisoning) with mitigations |
| **Limitation** | Broad survey rather than a SIEM-triage-specific evaluation; doesn't test on real SOC alert data |
| **Relevance to our project** | Broader context for where LLM-assisted triage sits in the wider generative-AI-in-cybersecurity landscape; its LLM-vulnerability catalog (esp. prompt injection) directly motivated our own input guardrail work (issue #8, #10) |

**Notes / Quotes:**
> Corrected 2026-08-14: this entry previously cited a non-existent arXiv ID (2407.08628) under the same first author. Verified against the actual arXiv record — the real Ferrag et al. paper is the one described above, at arXiv 2405.12750.

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
| **Venue** | Journal of Cybersecurity and Privacy (MDPI), Vol. 5, No. 4, Article 95 |
| **URL / DOI** | https://www.mdpi.com/2624-800x/5/4/95 |
| **Method** | Systematic literature survey of LLM/agent applications across SOC tasks (log summarization, alert triage, threat intel, incident response, report generation, asset discovery, vulnerability management) |
| **Dataset** | N/A (survey paper) |
| **Key result** | Maps the current SOC-automation landscape; finds human-AI collaboration outperforms full automation as the dominant successful pattern |
| **Limitation** | Survey-level synthesis — no novel empirical evaluation of its own |
| **Relevance to our project** | Gives us a taxonomy to position our copilot in the literature and justifies our human-in-the-loop design choice |

**Notes / Quotes:**
> Confirms human-AI collaboration, not full automation, is where the field is converging — supports our project's core design assumption.

---

## Paper 6 — Wazuh RAG-Driven SOC Copilot

| Field | Content |
|---|---|
| **Full title** | Enhancing Security Operations Center: Wazuh Security Event Response with Retrieval-Augmented-Generation-Driven Copilot |
| **Authors** | Ismail, Kurnia, Widyatama, Wibawa, Brata, Ukasyah, Nelistiani, Kim |
| **Year** | 2025 |
| **Venue** | Sensors (MDPI), Vol. 25, No. 3, Article 870 |
| **URL / DOI** | https://www.mdpi.com/1424-8220/25/3/870 |
| **Method** | RAG-driven LLM copilot built directly on top of the open-source Wazuh SIEM/XDR platform, enriching and responding to real Wazuh security events |
| **Dataset** | Live Wazuh alert stream (not a static benchmark) |
| **Key result** | Demonstrates the same core pattern we use (LLM + retrieval-augmented context over structured alerts) works against a real, live open-source SIEM rather than a static snapshot dataset |
| **Limitation** | Single-deployment case study; no comparison against a non-RAG or non-LLM baseline |
| **Relevance to our project** | **Closest architectural match found** — same LLM+RAG-over-alerts pattern as our LangGraph+MITRE-RAG pipeline, but grounded in Wazuh instead of GUIDE. Directly informed this week's Wazuh alert-adapter prototype (`src/integrations/wazuh_adapter.py`) |

**Notes / Quotes:**
> Confirms our architecture generalizes beyond a single static dataset — the same design works against a live open-source SIEM's alert format.

---

## Paper 7 — GeNIS Dataset

| Field | Content |
|---|---|
| **Full title** | GeNIS: A Modular Dataset for Network Intrusion Detection and Classification |
| **Authors** | Silva, Pinto, Vitorino, Gonçalves, Maia, Praça (GECAD, Polytechnic of Porto) |
| **Year** | 2025 |
| **Venue** | Data in Brief |
| **URL / DOI** | https://doi.org/10.1016/j.dib.2025.111487 |
| **Method** | Emulated small/medium-enterprise (SME) network on the Airbus CyberRange platform; captures benign traffic plus multi-stage attack scenarios, released as raw PCAPNG (37M+ packets) and labeled flow-level CSVs (2.8M+ flows) |
| **Dataset** | GeNIS itself — first dataset we found explicitly targeting the labeled-SME-traffic gap |
| **Key result** | Fills a documented scarcity of labeled datasets representative of SME network environments (most public IDS datasets target large-enterprise or generic traffic) |
| **Limitation** | Flow-level network schema, not incident/alert schema — structurally different from GUIDE, would need its own loader rather than reusing `src/data/load_data.py` as-is |
| **Relevance to our project** | Directly matches the "SME traffic" dataset gap flagged for this week's research; documented as a candidate second dataset in `datasets/README.md`, not yet integrated into training/eval pending a scoping decision |

**Notes / Quotes:**
> "There is a scarcity of labelled datasets focused on the cyberattacks that target vulnerable small and medium-sized enterprises" — the stated motivation for the dataset, which is exactly the gap our project's dataset search this week was trying to fill.

---

## Paper 8 — AI-Driven Security Alert Screening Survey

| Field | Content |
|---|---|
| **Full title** | AI-Driven Security Alert Screening and Alert Fatigue Mitigation in Security Operations Centers: A Survey |
| **Authors** | Ndichu, Ban, Ozawa, Takahashi, Inoue |
| **Year** | 2026 (submitted to ACM Computing Surveys) |
| **Venue** | arXiv |
| **URL / DOI** | https://arxiv.org/abs/2605.08316 |
| **Method** | Systematic survey (119 records, 87 core studies, 2015–2026) synthesizing AI-driven alert screening into a four-stage taxonomy (filtering, triage, correlation, generative augmentation); separately reviews 22 benchmark/alert-level datasets by research orientation (LLM / ML-DL / upstream-only) and their representational gaps vs. real SOC environments |
| **Dataset** | N/A (survey); catalogs 22 others |
| **Key result** | Positions human-AI-teaming, explainability, and dataset representativeness as the field's open problems — most existing alert-level datasets under-represent real SOC noise/imbalance |
| **Limitation** | Survey-level synthesis, no new empirical evaluation |
| **Relevance to our project** | Its dataset-gap taxonomy is the direct reference point for evaluating GeNIS and other 2025+ candidates against — and for articulating why GUIDE alone (a single 2024 snapshot) under-represents the "missing alert" / false-negative coverage problem flagged for this week |

**Notes / Quotes:**
> Confirms dataset representativeness (not just model choice) is a recognized open gap in this literature — directly supports evaluating a second, SME-focused dataset (GeNIS) alongside GUIDE.
>
> Corrected 2026-08-15: title updated from "...A Comprehensive Survey" to "...A Survey" — the paper's current arXiv version (v2) dropped "Comprehensive" from the title; the original entry cited the v1 title. Re-verified independently against the live arXiv abstract page rather than propagating the earlier entry.

---

## Reference Table (Quick Overview)

| # | Title (short) | Authors | Year | Method | Dataset | Relevance |
|---|---|---|---|---|---|---|
| 1 | Microsoft Security Copilot | Microsoft | 2024 | GPT-4 in SOC workflows | Internal threat intel | Industry benchmark |
| 2 | ADStrike | capture0x | 2025 | Agentic AI via MCP | N/A | Blue team counterpart |
| 3 | Generative AI in Cybersecurity | Ferrag et al. | 2024/25 | LLM survey across cybersecurity domains | N/A (review) | LLM-vulnerability catalog motivates our guardrails |
| 4 | CORTEX | Wei et al. | 2025 | Multi-agent LLM triage | Custom SOC traces | Closest architecture match |
| 5 | AI-Augmented SOC Survey | Srinivas et al. | 2025 | Literature survey | N/A | Positions project in field |
| 6 | Wazuh RAG-Driven SOC Copilot | MDPI Sensors | 2025 | LLM+RAG on live Wazuh alerts | Live Wazuh stream | Closest architecture match (live SIEM) |
| 7 | GeNIS Dataset | Silva et al. | 2025 | Emulated SME network capture | GeNIS (2.8M+ flows) | Fills SME-traffic dataset gap |
| 8 | Alert Screening Survey (arXiv v2 title: "...A Survey") | Ndichu et al. | 2026 | Literature survey, 22-dataset review | N/A | Dataset-representativeness reference point |

---

## Tools and Datasets Identified

## Paper 9 — Context Contamination in LLM Analysis of Network Security Logs

| Field | Content |
|---|---|
| **Full title** | Context Contamination in LLM Analysis of Network Security Logs: Poison with Passive Prompt Injection and Mitigation Evaluation |
| **Authors** | Karanjai, R.; Lu, Y.; Hegadehalli Madhavarao, H.; Xu, L.; Shi, W. |
| **Year** | 2026 |
| **Venue** | 35th USENIX Security Symposium (USENIX Security 26), Baltimore MD |
| **URL / DOI** | https://www.usenix.org/conference/usenixsecurity26/presentation/karanjai |
| **Method** | *Passive* prompt injection: payloads embedded in log-generating fields persist in storage and execute later, when an analyst queries the LLM. Introduces the LogInject framework and an adversarial log benchmark. |
| **Dataset** | LogInject-1.0 — log entries including adversarial samples; three production LLMs evaluated |
| **Key result** | Production LLMs used for log analysis are vulnerable across attack objectives including activity concealment and output hijacking |
| **Limitation** | Targets the model's analysis output; does not evaluate an architecture where a non-LLM component owns the decision |
| **Relevance to our project** | **The closest prior work to our §4.14 benchmark.** Same threat shape — payload arrives inside a telemetry field, not an analyst's prompt. Differs in what an attack can win: our §4.7 architecture means a successful injection corrupts an explanation but cannot change a verdict. Their unit is the log line; ours is the alert schema. |

**Notes:** Metadata verified against the USENIX programme page 2026-09-19, not recalled.

---

## Paper 10 — Let the Alerts Speak

| Field | Content |
|---|---|
| **Full title** | Let the Alerts Speak: LLM-Based IDS Alert Interpretation for SOC Triage |
| **Authors** | Schärmer, A.; Landauer, M.; Skopik, F.; Wurzenberger, M.; Squarcina, M. |
| **Year** | 2026 |
| **Venue** | ARES 2026 International Workshops, LNCS, pp. 346–364, Springer Nature Switzerland |
| **URL / DOI** | https://doi.org/10.1007/978-3-032-35579-9_19 |
| **Method** | LLM classification of IDS alerts to assist analysts during triage |
| **Dataset** | IDS alert data (not GUIDE) |
| **Key result** | LLMs can assist interpretation of high-volume IDS alerts, addressing analyst fatigue and false-positive burden |
| **Limitation** | IDS alerts carry human-readable rule descriptions — a far more favourable input than anonymised codes |
| **Relevance to our project** | Nearest comparable SOC-triage system. The contrast is the point: GUIDE's `AlertTitle` is a numeric ID, not prose, which §3.3 shows is decisive for what a language model can contribute. |

**Notes:** Metadata verified via Crossref 2026-09-19.

---

## Paper 11 — Datasheets for Datasets

| Field | Content |
|---|---|
| **Full title** | Datasheets for datasets |
| **Authors** | Gebru, T.; Morgenstern, J.; Vecchione, B.; Wortman Vaughan, J.; Wallach, H.; Daumé III, H.; Crawford, K. |
| **Year** | 2021 |
| **Venue** | Communications of the ACM 64(12), 86–92 |
| **URL / DOI** | https://doi.org/10.1145/3458723 |
| **Method** | Proposes a standard documentation record for datasets: motivation, composition, collection, preprocessing, uses, distribution, maintenance |
| **Key result** | Standardised dataset documentation improves transparency and reduces misuse |
| **Relevance to our project** | `docs/soc-injection-benchmark-datasheet.md` follows this format for our 400-attack benchmark. Cited, not merely gestured at. |

**Notes:** Metadata verified via Crossref 2026-09-19.

---

## Paper 12 — Dos and Don'ts of Machine Learning in Computer Security

| Field | Content |
|---|---|
| **Full title** | Dos and Don'ts of Machine Learning in Computer Security |
| **Authors** | Arp, D.; Quiring, E.; Pendlebury, F.; Warnecke, A.; Pierazzi, F.; Wressnegger, C.; Cavallaro, L.; Rieck, K. |
| **Year** | 2022 |
| **Venue** | 31st USENIX Security Symposium |
| **URL / DOI** | https://www.usenix.org/conference/usenixsecurity22/presentation/arp |
| **Method** | Identifies recurring pitfalls in learning-based security systems; reviews 30 papers from top-tier security venues |
| **Key result** | Sampling bias and data snooping are widespread in the security ML literature |
| **Relevance to our project** | The security-specific framing for §4.12. Our incident-level leakage is an instance of exactly the data-snooping pitfall catalogued here — and our own earlier numbers carried it undetected, which is the ordinary way this goes. |

**Notes:** Metadata verified against the USENIX programme page 2026-09-19.

---

## Paper 13 — Leakage and the Reproducibility Crisis in ML-based Science

| Field | Content |
|---|---|
| **Full title** | Leakage and the reproducibility crisis in machine-learning-based science |
| **Authors** | Kapoor, S.; Narayanan, A. |
| **Year** | 2023 |
| **Venue** | Patterns 4(9), 100804 (Elsevier) |
| **URL / DOI** | https://doi.org/10.1016/j.patter.2023.100804 |
| **Method** | Taxonomy of leakage types across scientific ML; survey of affected published work |
| **Key result** | Leakage is a leading cause of irreproducible ML results; non-independence between train and test rows is among the hardest variants to detect, because conventional checks still pass |
| **Relevance to our project** | The general framing for §4.12. Our contribution is a *measurement* on a specific corpus — +0.2433 from a labelled sibling, +0.0302 from the split rule over seven seeds — rather than another warning. |

**Notes:** Metadata verified via Crossref 2026-09-19.

---

| Name | Type | URL | Notes |
|---|---|---|---|
| GUIDE | Dataset | https://www.kaggle.com/datasets/Microsoft/microsoft-security-incident-prediction | Largest public real-world SOC alert/incident dataset — 1.6M alerts, 1M analyst-triaged incidents from 6,100+ orgs, released 2024 (CDLA-2.0). Replaces CICIDS2017, which is outdated network-flow data not designed for SOC/LLM triage. |
| ADStrike | Tool | https://github.com/capture0x/adstrike | Agentic red team tool, MCP-based |
| Microsoft Security Copilot | Tool | https://www.microsoft.com/en-us/security/business/ai-machine-learning/microsoft-copilot-for-security | Industry SOC copilot benchmark |
| Wazuh | Tool | https://wazuh.com/ | Open-source SIEM/XDR (indexer + server + dashboard + agent). A schema adapter mapping Wazuh alert JSON onto the GUIDE field shape was written and unit-tested against sample JSON — see `docs/wazuh-integration.md` and `src/integrations/wazuh_adapter.py`. **No live Wazuh server was ever deployed**, and the classifier behind the adapter is unvalidated on Wazuh-origin alerts (~62% missing features); "live alert source" would overstate what exists. |
| GeNIS | Dataset | https://doi.org/10.1016/j.dib.2025.111487 | SME-focused network-traffic dataset, released Mar 2025. Documented as a candidate second dataset in `datasets/README.md`; not yet integrated. |