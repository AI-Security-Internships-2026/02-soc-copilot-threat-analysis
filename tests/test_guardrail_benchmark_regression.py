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


# --- Issue #36 final review: the reduced denominator must stay visible -------
#
# L3 never returned a parseable verdict for 5 F4 rows. Its F4 recall is
# therefore over 50 rows while every other detector's F4 column is over 55.
# That was reported as a bare "100%" for a week. These three assertions fail if
# it goes silent again: in the per-cell denominators, in the published markdown,
# or in the cell count.

MATRIX_JSON = Path("experiments/results/m3_2_familywise_failure_analysis.json")
MATRIX_MD = Path("docs/m3-2-detector-family-matrix.md")

requires_matrix = pytest.mark.skipif(
    not MATRIX_JSON.exists(),
    reason="m3_2_familywise_failure_analysis.json not generated -- run experiments/m3_2_build_detector_matrix.py",
)


def _family_sizes() -> dict[str, int]:
    sizes: dict[str, int] = {}
    for row in _load_benchmark_rows():
        sizes[row["family"]] = sizes.get(row["family"], 0) + 1
    return sizes


@requires_learned
@requires_heuristic
def test_every_family_cell_denominator_equals_rows_actually_scored():
    """n + unscored == the family's true size, for every detector x family."""
    sizes = _family_sizes()
    combined = {
        **json.loads(LEARNED_JSON.read_text()),
        **json.loads(HEURISTIC_JSON.read_text()),
    }
    for key, entry in combined.items():
        if not isinstance(entry, dict) or "by_family" not in entry:
            continue
        unscored: dict[str, int] = {}
        for benchmark_id in entry.get("persistent_errors", {}):
            family = benchmark_id.split("_")[0]
            unscored[family] = unscored.get(family, 0) + 1
        for family, block in entry["by_family"].items():
            assert block["n"] + unscored.get(family, 0) == sizes[family], (
                f"{key}.{family}: scored {block['n']} + unscored "
                f"{unscored.get(family, 0)} != benchmark size {sizes[family]}"
            )
            assert block["detected"] <= block["n"], f"{key}.{family} detected > n"


@requires_matrix
def test_reduced_denominator_cells_are_flagged_in_the_published_matrix():
    summary = json.loads(MATRIX_JSON.read_text())
    reduced = summary["cells_with_reduced_denominator"]
    assert "l3.F4" in reduced, "L3's 5 unparseable F4 rows are no longer recorded"
    assert reduced["l3.F4"]["n_scored"] == 50
    assert reduced["l3.F4"]["n_unscored"] == 5

    markdown = MATRIX_MD.read_text()
    for cell, detail in reduced.items():
        for benchmark_id in detail["unscored_ids"]:
            assert benchmark_id in markdown, f"{cell}: {benchmark_id} not cited in the matrix"
    # The dagger is what a reader of the table itself sees.
    assert "†" in markdown


@requires_matrix
def test_matrix_is_seven_detectors_by_seven_families():
    summary = json.loads(MATRIX_JSON.read_text())
    assert len(summary["detectors_included"]) == 7
    assert summary["detectors_missing"] == []
    assert summary["n_cells"] == 49
