"""Tests for datasets/soc_injection_benchmark_v1.csv (issue #35, M3.1).

Asserts the committed CSV directly rather than re-running the generator --
the generator streams the 2.4GB GUIDE_train.csv and isn't something the
regular test suite should depend on being present.
"""

import csv
from collections import Counter
from pathlib import Path

BENCHMARK_CSV = Path("datasets/soc_injection_benchmark_v1.csv")

EXPECTED_FAMILY_COUNTS = {
    "F1": 60,
    "F2": 55,
    "F3": 60,
    "F4": 55,
    "F5": 50,
    "F6": 60,
    "F7": 60,
    "BCONTROL": 100,
}
VALID_FIELDS = {
    "AlertTitle", "Category", "MitreTechniques", "LastVerdict",
    "DeviceName", "SuspicionLevel", "ALL",
}


def _load_rows() -> list[dict]:
    with open(BENCHMARK_CSV, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_total_row_count_is_500():
    rows = _load_rows()
    assert len(rows) == 500


def test_family_counts_match_issue_35_exactly():
    rows = _load_rows()
    counts = Counter(row["family"] for row in rows)
    assert dict(counts) == EXPECTED_FAMILY_COUNTS


def test_exactly_100_benign_controls_flagged_correctly():
    rows = _load_rows()
    is_control = [row["is_benign_control"] == "True" for row in rows]
    assert sum(is_control) == 100
    for row in rows:
        expected = row["family"] == "BCONTROL"
        assert (row["is_benign_control"] == "True") == expected, row["benchmark_id"]


def test_benchmark_ids_are_unique():
    rows = _load_rows()
    ids = [row["benchmark_id"] for row in rows]
    assert len(ids) == len(set(ids))


def test_modified_field_values_are_real_guide_columns():
    rows = _load_rows()
    for row in rows:
        assert row["modified_field"] in VALID_FIELDS, row["benchmark_id"]


def test_expected_verdict_is_filled_for_every_row():
    rows = _load_rows()
    for row in rows:
        assert row["expected_verdict_if_successful"].strip(), row["benchmark_id"]


def test_attack_rows_have_a_nonempty_payload_and_controls_do_not():
    rows = _load_rows()
    for row in rows:
        if row["is_benign_control"] == "True":
            assert row["injected_payload"] == "", row["benchmark_id"]
            assert row["original_value_snippet"].strip(), row["benchmark_id"]
        else:
            assert row["injected_payload"].strip(), row["benchmark_id"]
