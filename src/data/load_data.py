"""
Loads GUIDE-format alert data, either:
  - the real dataset (download yourself per datasets/README.md), or
  - the synthetic sample at datasets/sample/guide_sample.csv (generated via
    `python -m src.data.generate_sample`)

Both have identical columns, so nothing downstream needs to change when you
swap in the real file.
"""

from pathlib import Path

import pandas as pd

from src.data.schema import ALL_RAW_COLUMNS

REAL_DATA_PATH = Path("datasets/GUIDE_train.csv")  # gitignored -- download yourself
SAMPLE_DATA_PATH = Path("datasets/sample/guide_sample.csv")


def load_alerts(path: Path | None = None) -> pd.DataFrame:
    """
    Load alert data. If `path` isn't given, prefers the real dataset if
    present, otherwise falls back to the synthetic sample.
    """
    if path is None:
        path = REAL_DATA_PATH if REAL_DATA_PATH.exists() else SAMPLE_DATA_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"No data found at {path}. Run `python -m src.data.generate_sample` "
            "to create a local sample, or download the real dataset (see "
            "datasets/README.md)."
        )

    df = pd.read_csv(path)

    missing = set(ALL_RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Loaded file is missing expected GUIDE columns: {missing}")

    print(f"Loaded {len(df)} rows from {path}")
    return df


if __name__ == "__main__":
    df = load_alerts()
    print(df.head())
    print(df["IncidentGrade"].value_counts())
