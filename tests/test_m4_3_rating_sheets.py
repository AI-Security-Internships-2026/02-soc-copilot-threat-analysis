"""Issue #40 (M4.3) PART A: the rating sheets must not leak the answer.

Same contract as tests/test_m3_1_rating_sheets.py enforces for the #35 packet.
Five raters score the same 200 rows, so the sheets must be identical except for
the rater letter, and nothing a rater sees may reveal which arm produced an
explanation or what the alert's true label is.

Skips cleanly when the package has not been built, since stage 2 needs live
model calls -- mirroring the skipif convention in
tests/test_guardrail_benchmark_regression.py.
"""

import csv
from pathlib import Path

import pytest

from experiments.m4_3_build_human_study_package import DIMENSIONS, RATERS, STRATA

RESULTS = Path("experiments/results")
SAMPLE = RESULTS / "m4_3_study_alerts.csv"
KEY = RESULTS / ".m4_3_variant_key.csv"
SHEETS = {r: RESULTS / f"m4_3_rating_sheet_rater{r}.csv" for r in RATERS}

requires_sample = pytest.mark.skipif(
    not SAMPLE.exists(),
    reason="m4_3_study_alerts.csv not generated -- run m4_3_build_human_study_package.py --sample",
)
requires_sheets = pytest.mark.skipif(
    not all(p.exists() for p in SHEETS.values()),
    reason="rating sheets not generated -- run m4_3_build_human_study_package.py --build-sheets",
)


def _read(path: Path) -> list[dict]:
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


@requires_sample
def test_sample_is_100_alerts_stratified_as_the_issue_specifies():
    rows = _read(SAMPLE)
    assert len(rows) == 100
    for grade, n in STRATA.items():
        assert sum(1 for r in rows if r["ground_truth"] == grade) == n


@requires_sheets
def test_every_rater_sheet_has_identical_items_in_identical_order():
    """Fleiss' kappa needs every rater scoring the same item -- a per-rater
    shuffle would make the sheets unpoolable."""
    reference = None
    for rater, path in SHEETS.items():
        rows = _read(path)
        assert len(rows) == 200, f"rater {rater}: {len(rows)} rows, expected 100 alerts x 2 variants"
        assert {r["rater"] for r in rows} == {rater}
        spine = [(r["row_id"], r["item_id"], r["variant_shown"], r["explanation_text"]) for r in rows]
        if reference is None:
            reference = spine
        else:
            assert spine == reference, f"rater {rater}'s sheet differs from rater A's"


@requires_sheets
def test_sheets_do_not_reveal_which_arm_or_the_true_label():
    leaking = {"variant_source", "ground_truth", "is_proposed", "baseline", "proposed"}
    for rater, path in SHEETS.items():
        with open(path, newline="") as handle:
            header = set(next(csv.reader(handle)))
        assert not (header & leaking), f"rater {rater}'s sheet exposes {header & leaking}"


@requires_sheets
def test_score_columns_are_blank_and_cover_all_four_dimensions():
    for path in SHEETS.values():
        rows = _read(path)
        for dimension in DIMENSIONS:
            assert all(r[dimension] == "" for r in rows), f"{dimension} pre-filled in {path.name}"
        assert all(r["rater_note"] == "" for r in rows)
    assert len(DIMENSIONS) == 4


@requires_sheets
def test_each_alert_contributes_exactly_one_baseline_and_one_proposed():
    """The paired Wilcoxon test needs both arms present for all 100 alerts."""
    key = _read(KEY)
    assert len(key) == 200
    by_item: dict[str, set[str]] = {}
    for row in key:
        by_item.setdefault(row["item_id"], set()).add(row["variant_source"])
    assert len(by_item) == 100
    assert all(sources == {"baseline", "proposed"} for sources in by_item.values())
    # Randomised, not alternating: a fixed A=baseline mapping would be guessable
    # from the first pair a rater happened to notice.
    shown_for_baseline = {r["variant_shown"] for r in key if r["variant_source"] == "baseline"}
    assert shown_for_baseline == {"A", "B"}


@requires_sheets
def test_the_variant_key_is_not_distributed():
    """The key is committed for reproducibility but dot-prefixed, so it is not
    picked up by a glob of the rater sheets."""
    assert KEY.name.startswith(".")
    assert not any(p.name.startswith(".") for p in SHEETS.values())
