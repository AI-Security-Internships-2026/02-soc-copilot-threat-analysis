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