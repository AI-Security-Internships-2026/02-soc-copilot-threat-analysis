"""
Column schema reference for the Microsoft GUIDE dataset
(Kaggle: "Microsoft Security Incident Prediction").

Source: GUIDE dataset documentation / public EDA notebooks. Used to keep
the sample generator, loader, and preprocessing code consistent with the
real dataset's column names so this pipeline works unchanged once the
full CSVs are downloaded from Kaggle.

Target variable: IncidentGrade -> {"TruePositive", "BenignPositive", "FalsePositive"}
"""

# Identifier columns -- useful for grouping/joins, but dropped before
# modelling to avoid leakage (they don't generalise to unseen orgs/incidents).
ID_COLUMNS = [
    "Id",
    "OrgId",
    "IncidentId",
    "AlertId",
    "DetectorId",
    "DeviceId",
]

# Raw categorical / descriptive columns.
CATEGORICAL_COLUMNS = [
    "AlertTitle",
    "Category",
    "MitreTechniques",
    "ActionGrouped",
    "ActionGranular",
    "EntityType",
    "EvidenceRole",
    "DeviceName",
    "CountryCode",
    "State",
    "City",
]

# Analyst-derived evidence fields. Sparsely populated in real GUIDE data
# (SuspicionLevel ~14%, LastVerdict ~22% non-null), and load-bearing for
# routing: src/agent/fallback_classifier.py counts how many of
# EVIDENCE_FIELDS an alert has and sends the sparse ones to the classifier.
# They are listed here so load_alerts() rejects a file that lacks them --
# datasets/sample/guide_sample.csv did, which silently pinned
# evidence_field_count at a maximum of 1 and made the LLM branch unreachable
# on every no-Kaggle-credentials run.
EVIDENCE_COLUMNS = [
    "SuspicionLevel",
    "LastVerdict",
]

# Raw timestamp column -- decomposed into engineered features at preprocess time.
TIMESTAMP_COLUMN = "Timestamp"

# Label column and its three valid values.
TARGET_COLUMN = "IncidentGrade"
TARGET_CLASSES = ["TruePositive", "BenignPositive", "FalsePositive"]

# Columns engineered downstream in preprocess.py
ENGINEERED_COLUMNS = ["Hour", "DayOfWeek", "Month"]

ALL_RAW_COLUMNS = (
    ID_COLUMNS + CATEGORICAL_COLUMNS + EVIDENCE_COLUMNS + [TIMESTAMP_COLUMN, TARGET_COLUMN]
)
