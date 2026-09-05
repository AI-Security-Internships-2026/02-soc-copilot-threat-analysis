# experiments/streaming_encode.py
#
# Memory-safe loader for large slices of GUIDE_train.csv.
#
# src/models/baseline.py loads its rows with a single pd.read_csv and holds the
# whole frame, with every categorical still a Python string, in memory at once.
# That is fine at the deployed 100,000-row default and is not fine at 1,000,000
# on an 8 GB machine: the raw object-dtype frame alone runs to several GB before
# any encoding happens.
#
# This module streams the file twice instead:
#
#   pass 1  collect the distinct values of each categorical column
#   pass 2  map them to integer codes and accumulate int32 arrays
#
# The codes are assigned by sorted order of the distinct values, which is
# exactly what sklearn's LabelEncoder does, so a model trained on this loader's
# output is interchangeable with one trained through src/data/preprocess.py and
# can be scored by src/data/preprocess.transform_with_encoders() unchanged. The
# encoders returned here are real LabelEncoder objects with classes_ populated,
# so the saved artifact has the same shape as experiments/results/baseline_model.joblib.
#
# It also returns the (OrgId, IncidentId) group key, which preprocess() cannot:
# that function drops the ID columns before returning, and incident-level
# splitting needs them.

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from src.data.schema import ID_COLUMNS, TARGET_COLUMN, TIMESTAMP_COLUMN

CHUNK_ROWS = 100_000
GROUP_COLUMNS = ["OrgId", "IncidentId"]


def _engineer(chunk: pd.DataFrame) -> pd.DataFrame:
    """Timestamp -> Hour/DayOfWeek/Month, matching src/data/preprocess.py."""
    ts = pd.to_datetime(chunk[TIMESTAMP_COLUMN], errors="coerce")
    chunk = chunk.drop(columns=[TIMESTAMP_COLUMN])
    chunk["Hour"] = ts.dt.hour
    chunk["DayOfWeek"] = ts.dt.dayofweek
    chunk["Month"] = ts.dt.month
    return chunk


def _read(path: Path, max_rows: int):
    """Yield label-bearing chunks until max_rows source rows have been read."""
    read = 0
    for chunk in pd.read_csv(path, chunksize=CHUNK_ROWS, low_memory=False):
        if read >= max_rows:
            break
        if read + len(chunk) > max_rows:
            chunk = chunk.iloc[: max_rows - read]
        read += len(chunk)
        yield chunk.dropna(subset=[TARGET_COLUMN])


def load_encoded(path: Path, max_rows: int, verbose: bool = True):
    """Return (X int32 frame, y, groups, encoders) for the first max_rows rows.

    X carries the same columns, in the same order, as src/data/preprocess.py
    produces, so it is directly comparable with the deployed baseline.
    """
    path = Path(path)

    # ---- pass 1: distinct values per categorical column -------------------
    uniques: dict[str, set] = {}
    n_rows = 0
    for i, chunk in enumerate(_read(path, max_rows), start=1):
        n_rows += len(chunk)
        features = chunk.drop(columns=[TARGET_COLUMN] + ID_COLUMNS)
        features = _engineer(features)
        for col in features.select_dtypes(include="object").columns:
            uniques.setdefault(col, set()).update(features[col].astype(str).unique())
        if verbose and i % 5 == 0:
            print(f"  pass 1: {n_rows:,} rows scanned", flush=True)

    encoders: dict[str, LabelEncoder] = {}
    codes: dict[str, dict] = {}
    for col, values in uniques.items():
        classes = np.array(sorted(values), dtype=object)
        encoder = LabelEncoder()
        encoder.classes_ = classes
        encoders[col] = encoder
        codes[col] = {value: index for index, value in enumerate(classes)}
    if verbose:
        print(f"  pass 1 done: {n_rows:,} labelled rows, {len(encoders)} categorical columns")

    # ---- pass 2: encode to int32 -----------------------------------------
    X_parts, y_parts, group_parts = [], [], []
    seen = 0
    for i, chunk in enumerate(_read(path, max_rows), start=1):
        seen += len(chunk)
        y_parts.append(chunk[TARGET_COLUMN].to_numpy())
        group_parts.append(
            chunk[GROUP_COLUMNS[0]].astype(str).to_numpy().astype(object)
            + "|"
            + chunk[GROUP_COLUMNS[1]].astype(str).to_numpy().astype(object)
        )
        features = chunk.drop(columns=[TARGET_COLUMN] + ID_COLUMNS)
        features = _engineer(features)
        for col in features.columns:
            if col in codes:
                features[col] = features[col].astype(str).map(codes[col]).astype("int32")
            else:
                # Numeric columns keep their NaNs. src/data/preprocess.py never
                # fills them and sklearn's forests handle missing values
                # natively, so imputing here would change the model rather than
                # just its memory footprint. float32 halves the footprint
                # without altering any split point at this range.
                features[col] = pd.to_numeric(features[col], errors="coerce").astype("float32")
        X_parts.append(features)
        if verbose and i % 5 == 0:
            print(f"  pass 2: {seen:,} rows encoded", flush=True)

    X = pd.concat(X_parts, ignore_index=True)
    y = pd.Series(np.concatenate(y_parts), name=TARGET_COLUMN)
    groups = np.concatenate(group_parts)
    if verbose:
        print(f"  loaded X{X.shape}, {len(np.unique(groups)):,} distinct incidents")
    return X, y, groups, encoders
