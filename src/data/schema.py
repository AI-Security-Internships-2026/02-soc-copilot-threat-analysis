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

# Raw timestamp column -- decomposed into engineered features at preprocess time.
TIMESTAMP_COLUMN = "Timestamp"

# Label column and its three valid values.
TARGET_COLUMN = "IncidentGrade"
TARGET_CLASSES = ["TruePositive", "BenignPositive", "FalsePositive"]

# Columns engineered downstream in preprocess.py
ENGINEERED_COLUMNS = ["Hour", "DayOfWeek", "Month"]

ALL_RAW_COLUMNS = (
    ID_COLUMNS + CATEGORICAL_COLUMNS + [TIMESTAMP_COLUMN, TARGET_COLUMN]
)
