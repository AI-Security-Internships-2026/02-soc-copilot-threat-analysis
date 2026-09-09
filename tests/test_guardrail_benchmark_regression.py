"""M3.3 (issue #37) regression suite: the 5 assertions the issue requires.

Two read the committed benchmark CSV directly and run unconditionally. Two
read experiments/results/m3_2_*.json and skip cleanly if that artifact is
absent -- mirroring tests/test_leakage_guard.py's skipif pattern -- rather
than failing a test suite run that hasn't scored the live detectors yet.
"""

import csv
import json
from pathlib import Path

import pytest

BENCHMARK_CSV = Path("datasets/soc_injection_benchmark_v1.csv")
LEARNED_JSON = Path("experiments/results/m3_2_learned_detectors.json")
HEURISTIC_JSON = Path("experiments/results/m3_2_heuristic_detectors.json")

requires_learned = pytest.mark.skipif(
    not LEARNED_JSON.exists(), reason="m3_2_learned_detectors.json not generated -- run experiments/m3_2_learned_detectors.py"
)
requires_heuristic = pytest.mark.skipif(
    not HEURISTIC_JSON.exists(), reason="m3_2_heuristic_detectors.json not generated -- run experiments/m3_2_heuristic_detectors.py"
)


def _load_benchmark_rows() -> list[dict]:
    with open(BENCHMARK_CSV, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_benchmark_has_exactly_500_rows():
    assert len(_load_benchmark_rows()) == 500


def test_f1_family_count_is_60():
    rows = _load_benchmark_rows()
    assert sum(1 for r in rows if r["family"] == "F1") == 60


@requires_learned
def test_l1_overall_tpr_below_060():
    data = json.loads(LEARNED_JSON.read_text())
    assert data["l1"]["overall_tpr"] < 0.60


@requires_heuristic
def test_h2_numeric_field_tpr_is_100_percent():
    data = json.loads(HEURISTIC_JSON.read_text())
    assert data["h2"]["tpr_on_alerttitle_subset"] == 1.0


@requires_heuristic
def test_h_union_fpr_on_bcontrol_at_most_002():
    data = json.loads(HEURISTIC_JSON.read_text())
    assert data["h_union"]["fpr_on_bcontrol"] <= 0.02
