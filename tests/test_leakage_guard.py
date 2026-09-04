"""Regression guards for the incident-level leakage finding.

experiments/incident_leakage_audit.py measured that on rows the model never
trained on, accuracy is 0.8325 when a labelled sibling from the same incident
was in training versus 0.5893 when none was -- a 24.3-point gap. That makes
the choice of evaluation sample a correctness property of the project, not a
stylistic one, and these tests pin the two facts that follow from it:

  1. The held-out sample really is held out (zero incident overlap). If a
     future change re-pointed the holdout evaluation at GUIDE_train.csv, the
     headline accuracy would silently inflate by roughly the gap above, and
     no existing test would notice.
  2. The train-sampled evaluation set really is contaminated, so anything
     describing it as clean is wrong.

Both need the 2.4GB GUIDE download and the generated sample caches, so both
skip cleanly on a fresh clone rather than failing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

TRAIN_PATH = Path("datasets/GUIDE_train.csv")
CACHE_DIR = Path("experiments/results/evaluation_samples")
TRAIN_SAMPLE = CACHE_DIR / "guide_balanced_333_per_class_seed_42.csv"
HELD_OUT_SAMPLE = CACHE_DIR / "guide_test_balanced_333_per_class_seed_42.csv"

# Mirrors src/models/baseline.py's DEFAULT_MAX_ROWS.
TRAINING_SLICE_ROWS = 100_000
INCIDENT_KEY = ["OrgId", "IncidentId"]

requires_guide = pytest.mark.skipif(
    not TRAIN_PATH.exists(), reason="GUIDE_train.csv not present (see datasets/README.md)"
)


def _training_incidents() -> set:
    slice_df = pd.read_csv(
        TRAIN_PATH, nrows=TRAINING_SLICE_ROWS, usecols=INCIDENT_KEY + ["IncidentGrade"]
    ).dropna(subset=["IncidentGrade"])
    return set(zip(slice_df["OrgId"], slice_df["IncidentId"]))


def _incident_overlap(sample_path: Path) -> tuple[int, int]:
    sample = pd.read_csv(sample_path, usecols=INCIDENT_KEY)
    keys = list(zip(sample["OrgId"], sample["IncidentId"]))
    training = _training_incidents()
    return sum(k in training for k in keys), len(keys)


@requires_guide
@pytest.mark.skipif(not HELD_OUT_SAMPLE.exists(), reason="held-out sample cache not generated")
def test_held_out_sample_shares_no_incident_with_the_training_slice():
    """The one leakage-free evaluation regime must stay leakage-free."""
    overlap, total = _incident_overlap(HELD_OUT_SAMPLE)
    assert overlap == 0, (
        f"{overlap}/{total} held-out alerts share an (OrgId, IncidentId) with the "
        "RF's training slice. The held-out evaluation is the only clean number in "
        "the project; if this fails, the sample is no longer drawn from "
        "GUIDE_Test.csv or the training slice has moved."
    )


@requires_guide
@pytest.mark.skipif(not TRAIN_SAMPLE.exists(), reason="train-sampled cache not generated")
def test_train_sampled_set_is_contaminated_and_known_to_be():
    """Pins the contamination so it cannot be quietly described as clean.

    This asserts a *defect* is still present, which is deliberate: the
    train-sampled figures remain in the paper as an in-distribution
    reference, and they are only honest while accompanied by this number.
    """
    overlap, total = _incident_overlap(TRAIN_SAMPLE)
    rate = overlap / total
    assert rate > 0.4, (
        f"train-sampled incident overlap is {rate:.2%} ({overlap}/{total}), well "
        "below the ~55.8% previously measured. If the sampling changed, every "
        "figure derived from this cache needs re-checking and the leakage "
        "discussion in the paper and docs/final-report.md needs updating."
    )


@requires_guide
def test_incident_label_is_constant_within_an_incident():
    """The premise the whole leakage argument rests on.

    If an incident could carry two different grades, a shared incident would
    leak nothing and the 24.3-point gap would need another explanation.
    """
    slice_df = pd.read_csv(
        TRAIN_PATH, nrows=TRAINING_SLICE_ROWS, usecols=INCIDENT_KEY + ["IncidentGrade"]
    ).dropna(subset=["IncidentGrade"])
    distinct = slice_df.groupby(INCIDENT_KEY)["IncidentGrade"].nunique()
    assert (distinct == 1).all(), (
        f"{int((distinct > 1).sum())} incidents carry more than one IncidentGrade. "
        "The leakage argument assumes the label is a function of the incident."
    )
