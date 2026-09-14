"""
Keeps the M6.1 manifest and compliance audit honest (issue #44).

The failure these guard against is silent: someone adds a result JSON, the
manifest does not mention it, and the paper's "every number is traceable" claim
quietly stops being true. Both scripts are pure functions of the committed
artifacts, so running them here costs nothing and fails the moment they drift.
"""

import importlib.util
from pathlib import Path


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path("experiments") / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_result_artifact_is_claimed_by_the_manifest():
    # check(), not build() -- build() rewrites the manifest, whose header carries
    # the current commit SHA, so running the suite would dirty the working tree.
    missing, unclaimed = _load("m6_1_build_manifest").check()
    assert not missing, f"manifest names artifacts that do not exist: {missing}"
    assert not unclaimed, (
        f"these artifacts exist but no manifest entry claims them: {unclaimed}. "
        "Add an entry, or move the file to experiments/results/archive/."
    )


def test_statistical_compliance_has_no_open_items():
    # audit() also writes; it is deterministic and carries no SHA, so the
    # rewrite is byte-identical and leaves the tree clean.
    pct, compliant, checked, exempt, open_items = _load("m6_1_compliance_audit").audit()
    assert not open_items, f"open statistical compliance items: {open_items}"
    assert pct == 100.0, f"compliance dropped to {pct:.1f}%"
    assert exempt > 0, "exemptions vanished -- did a rule stop being applied?"


def test_mcnemar_odds_ratio_excludes_one_where_p_is_significant():
    """An effect size that contradicts its own p-value means one of them is wrong."""
    import json
    d = json.loads(Path("experiments/results/m6_1_effect_sizes.json").read_text())
    rf = d["mcnemar_effect_sizes"]["rf_vs_llm_209"]
    assert rf["p_value"] < 0.001
    assert rf["ci_lower"] > 1.0, "p is significant but the OR interval includes 1"
    assert rf["odds_ratio"] == 105 / 27 or abs(rf["odds_ratio"] - 105 / 27) < 1e-3


def test_holm_correction_is_monotone_and_at_least_as_large_as_raw():
    import json
    d = json.loads(Path("experiments/results/m6_1_effect_sizes.json").read_text())
    res = d["multiplicity"]["m2_4_classifier_pairwise"]["results"]
    adj = [r["p_adjusted"] for r in res]
    assert adj == sorted(adj), "Holm-adjusted p-values must be monotone in rank"
    for r in res:
        assert r["p_adjusted"] >= r["p_raw"], "a correction may not shrink a p-value"


def test_data_availability_does_not_claim_uncollected_human_ratings():
    """M4.3 PART A has no raters yet; the statement must not imply the data exists."""
    text = Path("docs/data_availability.md").read_text().lower()
    assert "do not exist yet" in text or "has not been collected" in text
