"""Tests for src/agent/schema_guardrail.py (issue #10, week 9).

Promotes the manual checks described in docs/weekly-progress.md's Week 9
section -- "20 realistic numeric IDs (benign) vs. the 20 injection strings
from the Week 8 eval set (attack) -- 100% accuracy" -- into an assertion
that actually runs, instead of only living as prose in a log file.
"""

import csv
from pathlib import Path

from src.agent.schema_guardrail import validate_field_types

INJECTION_STRINGS_PATH = Path("experiments/soc_domain_eval_v1.csv")


def _load_injection_strings() -> list[str]:
    with open(INJECTION_STRINGS_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [row["text"] for row in rows if row["label"] == "injection"]


REALISTIC_NUMERIC_IDS = [
    45654, 99614, 111349, 56759, 12345, 7, 999999, 100000, 1, 42,
    "45654", "12345", "7", "999999", "100000", 0, 8675309, 314159, 271828, 161803,
]


def test_realistic_numeric_ids_pass():
    for value in REALISTIC_NUMERIC_IDS:
        reasons = validate_field_types({"AlertTitle": value, "DetectorId": value})
        assert reasons == [], f"valid numeric ID {value!r} was incorrectly flagged: {reasons}"


def test_injection_strings_are_all_flagged():
    injection_strings = _load_injection_strings()
    assert len(injection_strings) == 20, "expected the 20-row Week 8 injection set"
    for text in injection_strings:
        reasons = validate_field_types({"AlertTitle": text, "DetectorId": 10})
        assert reasons == ["non_numeric_field:AlertTitle"], (
            f"injection payload was not flagged as non-numeric: {text!r}"
        )


def test_missing_or_none_fields_are_not_flagged():
    assert validate_field_types({}) == []
    assert validate_field_types({"AlertTitle": None, "DetectorId": None}) == []


def test_full_20v20_synthetic_set_scores_100_percent():
    """Reproduces the exact accuracy claim from the Week 9 log.

    This 100% is true BY CONSTRUCTION, not empirically discovered, and the
    distinction matters wherever the figure is cited. The check is
    `int(value)`: no English sentence parses as an integer, so no prose
    payload can pass it, and no numeric ID can fail it. The test therefore
    confirms the guardrail is wired up and its corpus is well-formed -- it
    cannot fail for any rephrasing of an attack, and so it is not evidence
    that the guardrail generalises to attackers.

    What it does establish is the property the design actually claims: a
    type constraint cannot be evaded by rewording, because the rewording is
    still not an integer. The real limit is scope, not accuracy -- the
    guardrail only protects fields the schema genuinely constrains, which is
    why experiments/schema_guardrail_eval.py separately measures the false-
    positive rate against 5,000 real GUIDE AlertTitle values.
    """
    benign = REALISTIC_NUMERIC_IDS[:20]
    injection = _load_injection_strings()
    assert len(benign) == 20
    assert len(injection) == 20

    false_positives = sum(1 for v in benign if validate_field_types({"AlertTitle": v}))
    false_negatives = sum(1 for v in injection if not validate_field_types({"AlertTitle": v}))

    assert false_positives == 0
    assert false_negatives == 0
