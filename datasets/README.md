# Datasets

## Policy

**Do NOT commit raw datasets to this repository.**
Large files slow down Git, may violate data licences, and create GDPR risks.

## How to document your dataset

For every dataset you use, create a file `datasets/<dataset-name>.md` with the following fields:

```markdown
## Dataset Name

- **Source URL:** https://...
- **Licence:** (e.g. CC BY 4.0, MIT, custom — always verify!)
- **Version / date downloaded:** 2026-06-22
- **Size:** (approximate: rows, GB)
- **Format:** (CSV, PCAP, JSON, HDF5, …)
- **Download command / script:** (e.g. `wget https://...`)
- **Preprocessing steps:**
  1. Step one
  2. Step two
- **Train / Val / Test split:**
- **Notes:**
```

## Recommended storage options

| Option | When to use |
|---|---|
| Local disk only | Small experiments (< 500 MB) |
| University NAS / HPC scratch | Medium datasets shared within the lab |
| Hugging Face Datasets | Public NLP/ML datasets |
| Zenodo | Archived research datasets with DOI |
| DVC (Data Version Control) | Any dataset tracked alongside code |

## Example: CIC-IDS-2017

- **Source URL:** https://www.unb.ca/cic/datasets/ids-2017.html
- **Licence:** Research use — see website
- **Format:** PCAP + CSV
- **Preprocessing:** Extract flow features with CICFlowMeter

## GUIDE Dataset (Primary)

- **Source URL:** https://www.kaggle.com/datasets/Microsoft/microsoft-security-incident-prediction
- **Licence:** CDLA-2.0
- **Version / date downloaded:** 2024-07-11. Source: the `modified_ns` field recorded in `experiments/results/evaluation_samples/guide_balanced_333_per_class_seed_42.json`, whose `size_bytes` (2,425,409,087) still matches the file exactly — so the data has not changed since the evaluation samples were drawn. Kaggle exposes no version tag for this dataset.
- **Size:** `GUIDE_train.csv` 2.4 GB / **9,516,837 rows**; `GUIDE_Test.csv` 1.09 GB / **4,147,992 rows**; 45 columns. (The 13M evidences / 1.6M alerts / 1M incidents figures are the dataset paper's, counted at evidence and incident level rather than the alert-row level used here.)
- **Class distribution (`IncidentGrade`, full train file, counted directly):** BenignPositive 43.20%, TruePositive 34.91%, FalsePositive 21.35%, missing 0.54%
- **Format:** CSV
- **Download command / script:**
```bash
  kaggle datasets download -d Microsoft/microsoft-security-incident-prediction -p datasets/
  unzip datasets/microsoft-security-incident-prediction.zip -d datasets/
```
- **Preprocessing steps:**
  1. Drop leakage-prone ID columns (see `src/data/preprocess.py`)
  2. Decompose `Timestamp` into Hour/DayOfWeek/Month
  3. Label-encode categorical columns
- **Train / Val / Test split:** ⚠️ **Not currently using GUIDE's provided split.** This line previously claimed we were; that was inaccurate and is corrected here. `GUIDE_Test.csv` is downloaded but **never read by any code in this repository** (verified by grep across `src/`, `experiments/` and `tests/`). Everything — the Random Forest's train/test split and every agent evaluation sample — is drawn from `GUIDE_train.csv`:
  - Baseline: first 100,000 rows, split 80/20 stratified (`random_state=42`) → 79,580 train / 19,895 test (`src/models/baseline.py`).
  - Agent evaluation: class-balanced samples drawn by a seeded streaming pass over all 9.5M rows (`src/agent/evaluate.py`, seed 42), cached under `experiments/results/evaluation_samples/`.
  - These two are disjoint in practice but not by construction. Measured exact-row overlap between the 209-alert evaluation subset and the baseline's training slice is 4/209 (1.91%), consistent with chance — see `experiments/results/rf_vs_llm_control.json`.
  - **Moving evaluation onto `GUIDE_Test.csv` is the project's top outstanding methodological item** (`docs/final-report.md` §6.2, `docs/weekly-progress.md` Week 15).
- **Notes:** A synthetic sample matching this schema lives at `datasets/sample/guide_sample.csv` for local dev without the full download (see `src/data/generate_sample.py`). Note its `AlertTitle` values were non-numeric until Week 15, which the schema guardrail blocked 100% of — regenerate any sample created before then.

## GeNIS Dataset (Candidate — proposed, not yet integrated)

Found while researching 2025+ SOC/network datasets addressing the "SME traffic" gap flagged for
Week 10 (see `docs/literature-review.md` Paper 7 and `docs/weekly-progress.md` Week 10 section for
the full research trail). **Not yet downloaded or wired into training/eval** — documented here so
the decision to adopt it as a second dataset can go through review rather than being made silently.

- **Source URL:** https://doi.org/10.1016/j.dib.2025.111487 (GECAD, Polytechnic of Porto)
- **Licence:** Verify on download — Data in Brief articles are typically CC BY 4.0, but confirm
  against the actual dataset landing page before use.
- **Version / date downloaded:** _not yet downloaded_
- **Size:** ~37M packets (raw PCAPNG) / ~2.8M labeled flows (CSV)
- **Format:** PCAPNG (raw) + CSV (filtered, flow-level, statistical features)
- **Why it's a candidate:** built specifically to address the scarcity of labeled datasets for
  small/medium-enterprise (SME) network environments — an emulated SME network on the Airbus
  CyberRange platform, with benign traffic plus multi-stage attack scenarios (published Mar 2025).
- **Preprocessing steps (planned, not yet built):**
  1. GeNIS's schema is **flow-level network features** (statistical features per flow), not
     GUIDE's **incident/alert-level** schema (`AlertTitle`, `Category`, `MitreTechniques`, etc.) —
     these are structurally different problems. `src/data/load_data.py` / `schema.py` as they
     exist today are GUIDE-specific and would not work unchanged against GeNIS.
  2. Integrating GeNIS would need its own `src/data/genis_schema.py` + loader, mirroring the
     pattern already used for GUIDE, rather than extending the existing loader.
  3. Recommend scoping this as its own follow-up task once there's sign-off on which pipeline
     stage GeNIS would feed (a second evaluation dataset for the existing triage agent? A
     separate flow-level pre-filter stage ahead of the current alert-level triage?) — that
     decision changes the shape of the loader significantly.
- **Train / Val / Test split:** Not yet determined — depends on the integration approach above.
- **Notes:** See `docs/wazuh-integration.md` for a related but separate research thread (a live
  alert source rather than a labeled offline dataset) investigated the same week.