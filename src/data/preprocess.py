"""
Cleaning + feature engineering for GUIDE-format alert data.

Steps (informed by published GUIDE preprocessing approaches):
  1. Drop pure identifier columns (Id, OrgId, IncidentId, AlertId, DetectorId,
     DeviceId) -- these don't generalise to unseen orgs/devices and cause
     data leakage if kept.
  2. Decompose Timestamp into Hour / DayOfWeek / Month.
  3. Label-encode categorical columns.
  4. Drop rows with a missing target.
"""

import pandas as pd
from sklearn.preprocessing import LabelEncoder

from src.data.schema import (
    CATEGORICAL_COLUMNS,
    ID_COLUMNS,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
)


def engineer_timestamp_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    ts = pd.to_datetime(df[TIMESTAMP_COLUMN])
    df["Hour"] = ts.dt.hour
    df["DayOfWeek"] = ts.dt.dayofweek
    df["Month"] = ts.dt.month
    return df.drop(columns=[TIMESTAMP_COLUMN])


def encode_categoricals(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    encoders = {}
    for col in CATEGORICAL_COLUMNS:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
        encoders[col] = le
    return df, encoders


def preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, dict]:
    """
    Returns (X, y, encoders) ready for model training.
    """
    df = df.dropna(subset=[TARGET_COLUMN]).copy()

    y = df[TARGET_COLUMN]
    X = df.drop(columns=[TARGET_COLUMN] + ID_COLUMNS)

    X = engineer_timestamp_features(X)
    X, encoders = encode_categoricals(X)

    return X, y, encoders


if __name__ == "__main__":
    from src.data.load_data import load_alerts

    raw = load_alerts()
    X, y, _ = preprocess(raw)
    print(f"Features: {list(X.columns)}")
    print(f"X shape: {X.shape}, y shape: {y.shape}")
