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
- **Version / date downloaded:** _[fill in when you download]_
- **Size:** ~2.4 GB (train CSV), 45 features, 13M evidences / 1.6M alerts / 1M incidents
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
- **Train / Val / Test split:** Using GUIDE's provided train/test split
- **Notes:** A synthetic sample matching this schema lives at `datasets/sample/guide_sample.csv` for local dev without the full download (see `src/data/generate_sample.py`)

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