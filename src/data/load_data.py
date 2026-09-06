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


def load_alerts(path: Path | None = None, nrows: int | None = None) -> pd.DataFrame:
    """
    Load alert data. If `path` isn't given, prefers the real dataset if
    present, otherwise falls back to the synthetic sample.
    """
    if path is None:
        path = REAL_DATA_PATH if REAL_DATA_PATH.exists() else SAMPLE_DATA_PATH
        if path == SAMPLE_DATA_PATH:
            # This fallback used to be silent, which is how
            # experiments/results/agent_metrics.json came to sit alongside
            # the real results at 0.375 accuracy with nothing recording that
            # its labels were random noise. generate_sample.py assigns
            # IncidentGrade with random.choices() independently of every
            # feature, so nothing trained or evaluated on it means anything.
            print(
                "\n" + "!" * 72
                + f"\nWARNING: {REAL_DATA_PATH} not found -- falling back to {SAMPLE_DATA_PATH}."
                "\nThat file is SYNTHETIC: its labels are assigned at random and carry no"
                "\nrelationship to any feature. It exists to exercise the code path, not to"
                "\nproduce results. Do not report any metric derived from it."
                "\n" + "!" * 72 + "\n"
            )

    if not path.exists():
        raise FileNotFoundError(
            f"No data found at {path}. Run `python -m src.data.generate_sample` "
            "to create a local sample, or download the real dataset (see "
            "datasets/README.md)."
        )

    df = pd.read_csv(path, nrows=nrows)

    missing = set(ALL_RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Loaded file is missing expected GUIDE columns: {missing}")

    limit_note = f" (limited to {nrows:,} rows)" if nrows is not None else ""
    print(f"Loaded {len(df):,} rows from {path}{limit_note}")
    return df


if __name__ == "__main__":
    df = load_alerts()
    print(df.head())
    print(df["IncidentGrade"].value_counts())
