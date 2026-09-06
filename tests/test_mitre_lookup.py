"""Tests for src/agent/mitre_lookup.py technique-id parsing.

Week 15 found the parser split multi-technique values on "," while GUIDE
separates them with ";". In the committed 999-alert evaluation sample, 232 of
the 428 alerts carrying a MitreTechniques value use ";" and none use ",", so a
value like "T1078;T1078.004" was looked up whole, missed the technique map, and
returned an empty string. Over half of all alerts with ATT&CK data silently
lost their enrichment, and nothing in the output distinguished that from an
alert that genuinely had no technique listed.

These tests pin the parsing behaviour without needing the 30 MB ATT&CK bundle,
by passing an explicit technique map.
"""

import pytest

from src.agent.mitre_lookup import MAX_TECHNIQUES_IN_CONTEXT, get_technique_info

FAKE_MAP = {
    "T1078": {"name": "Valid Accounts", "description": "Adversaries may abuse valid accounts."},
    "T1078.004": {"name": "Cloud Accounts", "description": "Adversaries may abuse cloud accounts."},
    "T1110": {"name": "Brute Force", "description": "Adversaries may use brute force."},
    "T1110.003": {"name": "Password Spraying", "description": "Adversaries may spray passwords."},
    "T1110.001": {"name": "Password Guessing", "description": "Adversaries may guess passwords."},
    "T1566.002": {"name": "Spearphishing Link", "description": "Adversaries may send links."},
}


def test_single_technique_resolves():
    assert "Valid Accounts" in get_technique_info("T1078", FAKE_MAP)


def test_semicolon_separated_value_resolves():
    """The exact real-data shape the old comma-only parser dropped."""
    result = get_technique_info("T1078;T1078.004", FAKE_MAP)
    assert "Valid Accounts" in result
    assert "Cloud Accounts" in result, (
        "sub-technique after the ';' was dropped -- this is the bug that cost "
        "54% of enrichable alerts their ATT&CK context"
    )


def test_comma_separated_value_still_resolves():
    """Backwards compatible: the docstring's original example must keep working."""
    assert "Valid Accounts" in get_technique_info("T1078,T1078.004", FAKE_MAP)


def test_expansion_is_capped():
    """Long technique lists must not crowd the alert's own fields out of the prompt."""
    result = get_technique_info("T1110;T1110.003;T1110.001;T1078;T1566.002", FAKE_MAP)
    assert len(result.splitlines()) == MAX_TECHNIQUES_IN_CONTEXT


def test_unknown_ids_are_skipped_not_fatal():
    """An id absent from the map must not suppress the ones that are present."""
    assert "Valid Accounts" in get_technique_info("T9999;T1078", FAKE_MAP)


def test_whitespace_is_tolerated():
    assert "Valid Accounts" in get_technique_info("  T1078 ; T1078.004  ", FAKE_MAP)


@pytest.mark.parametrize("value", ["", "   ", None, 12345, float("nan")])
def test_missing_or_non_string_values_return_empty(value):
    """GUIDE leaves this field NaN on most alerts; that must not raise."""
    assert get_technique_info(value, FAKE_MAP) == ""


def test_entirely_unknown_value_returns_empty():
    assert get_technique_info("T9999;T8888", FAKE_MAP) == ""
