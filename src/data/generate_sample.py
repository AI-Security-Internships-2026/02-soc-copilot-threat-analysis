"""
Generates a small synthetic sample that mirrors the column structure of the
real Microsoft GUIDE dataset.

Why this exists: the real GUIDE train CSV is ~2.4 GB and lives on Kaggle
behind auth, and the repo's .gitignore correctly excludes large datasets.
This script produces a small, structurally-accurate CSV so the rest of the
pipeline (load_data.py, preprocess.py, models/baseline.py) can be developed,
run, and reviewed by a supervisor without anyone needing Kaggle credentials.

Once the real dataset is downloaded (see datasets/README.md), point
load_data.py at the real CSV instead -- no other code changes needed,
since column names match.

Usage:
    python -m src.data.generate_sample --rows 5000
"""

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.data.schema import TARGET_CLASSES

SAMPLE_PATH = Path("datasets/sample/guide_sample.csv")

CATEGORIES = ["InitialAccess", "Execution", "Persistence", "Exfiltration", "Impact", "Discovery"]
MITRE_TECHNIQUES = ["T1078", "T1059", "T1547", "T1041", "T1486", "T1087", "T1110"]
ACTIONS_GROUPED = ["Blocked", "Quarantined", "NoAction", "Investigated"]
ENTITY_TYPES = ["User", "Ip", "Device", "Mailbox", "File", "Process"]
EVIDENCE_ROLES = ["Impacted", "Related", "Attacker"]
COUNTRIES = ["US", "GB", "PK", "DE", "IN", "AE"]


# Observed values in datasets/GUIDE_train.csv.
SUSPICION_LEVELS = ["Suspicious"]
LAST_VERDICTS = ["Suspicious", "Malicious", "NoThreatsFound"]


def _random_timestamp(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def generate(n_rows: int, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    start = datetime(2024, 1, 1)
    end = datetime(2024, 6, 30)

    rows = []
    for i in range(n_rows):
        org_id = random.randint(1, 200)
        incident_id = random.randint(1, n_rows // 3 + 1)
        ts = _random_timestamp(start, end)
        rows.append(
            {
                "Id": i,
                "OrgId": org_id,
                "IncidentId": incident_id,
                "AlertId": random.randint(1, n_rows * 2),
                "DetectorId": random.randint(1, 500),
                "DeviceId": random.randint(1, 1000),
                "Timestamp": ts.isoformat(),
                # Numeric, matching real GUIDE data. This used to be
                # f"Alert_{n}", which is not int-parseable, so the schema
                # guardrail (EXPECTED_NUMERIC_FIELDS in
                # src/agent/schema_guardrail.py) blocked 100% of the synthetic
                # alerts. Anyone following the documented no-Kaggle-credentials
                # path got every alert held for human review with no verdict,
                # which the evaluator then scored as roughly chance accuracy --
                # a broken configuration that looked like a weak model.
                "AlertTitle": random.randint(1, 80),
                "Category": random.choice(CATEGORIES),
                "MitreTechniques": random.choice(MITRE_TECHNIQUES),
                "ActionGrouped": random.choice(ACTIONS_GROUPED),
                "ActionGranular": random.choice(ACTIONS_GROUPED) + "_detail",
                "EntityType": random.choice(ENTITY_TYPES),
                "EvidenceRole": random.choice(EVIDENCE_ROLES),
                "DeviceName": f"DEVICE-{random.randint(1, 1000)}",
                "CountryCode": random.choice(COUNTRIES),
                "State": "NA",
                "City": "NA",
                # Analyst-derived, and sparse in real GUIDE (~14% / ~22%
                # non-null). Emitted at roughly that rate rather than always
                # populated, because src/agent/fallback_classifier.py routes
                # on how many of these are present: a sample that always has
                # them would send everything to the LLM, and a sample missing
                # them entirely -- which this generator previously produced --
                # sends everything to the RF and makes the LLM branch
                # unreachable. Neither exercises the routing decision.
                "SuspicionLevel": (
                    random.choice(SUSPICION_LEVELS) if random.random() < 0.14 else None
                ),
                "LastVerdict": (
                    random.choice(LAST_VERDICTS) if random.random() < 0.22 else None
                ),
                "IncidentGrade": random.choices(
                    TARGET_CLASSES, weights=[0.25, 0.35, 0.40]
                )[0],
            }
        )

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic GUIDE-style sample CSV.")
    parser.add_argument("--rows", type=int, default=5000, help="Number of rows to generate.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = generate(args.rows, args.seed)
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAMPLE_PATH, index=False)
    print(f"Wrote {len(df)} synthetic rows to {SAMPLE_PATH}")


if __name__ == "__main__":
    main()
