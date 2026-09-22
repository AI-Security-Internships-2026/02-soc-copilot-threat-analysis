"""Blinding and scoring checks for the M3.1 interrater pass (issue #35).

The two rating sheets go to outside raters, so the thing worth testing is
what they *don't* contain: any route back to the ground-truth label. The
scoring side is checked for the breakdown the supervisor asked for -- number
of disagreements and how they distribute across benign/F1-F7.
"""

import csv
from pathlib import Path

import pytest

from experiments.m3_1_interrater_kappa import disagreement_distribution

SHEETS = [
    Path("experiments/results/m3_1_rating_sheet_raterA.csv"),
    Path("experiments/results/m3_1_rating_sheet_raterB.csv"),
]
KEY = Path("experiments/results/.m3_1_rating_worksheet_key.csv")

# Anything that would hand a rater the answer: the label itself, the
# benchmark id (its prefix *is* the family), the family, and the field name
# (every benign control is an AlertTitle row, and only attacks span 'ALL').
LEAKING_COLUMNS = {
    "true_label",
    "benchmark_id",
    "family",
    "is_benign_control",
    "expected_verdict_if_successful",
    "modified_field",
    "notes",
}


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        pytest.skip(f"{path} not generated -- run experiments/m3_1_build_rating_worksheet.py")
    with open(path) as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.stem)
def test_rating_sheet_carries_no_route_back_to_the_label(sheet):
    rows = _rows(sheet)
    assert rows, f"{sheet} is empty"
    assert not LEAKING_COLUMNS & set(rows[0]), f"{sheet} exposes ground truth"
    # The worksheet_id must not encode the family either -- W001, not F3_001.
    assert all(r["worksheet_id"].startswith("W") for r in rows)


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.stem)
def test_rating_sheet_arrives_blank_and_complete(sheet):
    rows = _rows(sheet)
    assert len(rows) == 100
    assert all(r["verdict"] == "" for r in rows), "a verdict was pre-filled"


def test_both_sheets_hold_identical_items_in_identical_order():
    a, b = (_rows(s) for s in SHEETS)
    assert [r["worksheet_id"] for r in a] == [r["worksheet_id"] for r in b]
    assert [r["text_shown"] for r in a] == [r["text_shown"] for r in b]
    # ...and differ only in the pre-filled rater column, so a returned file
    # is self-identifying.
    assert {r["rater"] for r in a} == {"A"}
    assert {r["rater"] for r in b} == {"B"}


def test_sheets_cover_exactly_the_scored_key():
    key = _rows(KEY)
    for sheet in SHEETS:
        assert [r["worksheet_id"] for r in _rows(sheet)] == [r["worksheet_id"] for r in key]


def test_disagreement_distribution_splits_by_family_and_totals_correctly():
    key_rows = [
        {"benchmark_id": "F3_001", "worksheet_id": "W1"},
        {"benchmark_id": "F3_002", "worksheet_id": "W2"},
        {"benchmark_id": "BCONTROL_001", "worksheet_id": "W3"},
    ]
    dist = disagreement_distribution(key_rows, ["W2"])

    assert dist["F3"]["n_disagreements"] == 1
    assert dist["F3"]["worksheet_ids"] == ["W2"]
    assert dist["F3"]["disagreement_rate"] == 0.5
    assert dist["BCONTROL"]["n_disagreements"] == 0
    assert sum(b["n_items"] for b in dist.values()) == len(key_rows)
    assert sum(b["n_disagreements"] for b in dist.values()) == 1


def test_disagreement_distribution_is_empty_when_raters_agree_everywhere():
    key_rows = [{"benchmark_id": "F1_001", "worksheet_id": "W1"}]
    dist = disagreement_distribution(key_rows, [])
    assert dist["F1"]["n_disagreements"] == 0
    assert dist["F1"]["disagreement_rate"] == 0.0
