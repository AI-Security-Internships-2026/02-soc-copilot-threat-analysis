"""
Guards the headline figures the demo and the write-ups quote against the
committed JSON they are supposed to come from.

This exists because the Week 21 demo caught two drifts that nothing else would
have: a headroom figure quoting the held-out-optimised arm instead of the
selected one, and a demo script narrating a review-gate hold for form values
that are actually auto-accepted. Both were wrong in the direction that flatters
the project, which is the direction worth testing.

A number appearing here means some document states it. If a result is
legitimately regenerated and a value moves, update the document and this file
together -- never just this file.
"""

import json
import re
from pathlib import Path

import pytest

RESULTS = Path("experiments/results")
DOCS = Path("docs")


def load(name):
    return json.loads((RESULTS / name).read_text())


def test_split_method_delta_is_replicated_across_seeds():
    """The paper's headline leakage claim: 7/7 seeds, same direction."""
    d = load("m2_1_splitmethod_delta_5seeds.json")
    per_seed = d["per_seed"]
    assert len(per_seed) == 7, "documents say seven seeds"

    # every seed must favour the leaky split -- "never once the reverse"
    for s in per_seed:
        row = s["row_level_split"]["accuracy"]
        grp = s["group_level_split"]["accuracy"]
        assert row > grp, f"seed {s['seed']}: row {row} !> group {grp}"

    agg = d["aggregate_delta_acc"]
    assert round(agg["mean"], 4) == 0.0302
    assert round(agg["ci_lower"], 4) == 0.0244
    assert round(agg["ci_upper"], 4) == 0.0351
    assert round(d["wilcoxon_delta_acc_vs_zero"]["p_value"], 4) == 0.0156


def test_headroom_headline_quotes_the_selected_arm_not_the_held_out_best():
    """+3.43 is the selection rule's arm; +3.6 is the one chosen by reading
    the held-out split the study promises not to optimise against."""
    sel = load("classifier_improvement_study.json")["selection"]
    assert round(sel["accuracy_gain_vs_deployed"], 4) == 0.0343

    deployed = load("classifier_improvement_study.json")["deployed_reference"]
    best_ref = sel["best_held_out_accuracy_for_reference"]
    assert round(best_ref - deployed["held_out_accuracy"], 4) == 0.0357, (
        "the 'reference' gap is the ~3.6 figure; it must stay distinguishable "
        "from the selected arm's 3.43"
    )

    # the documents must not present 3.6 as the headline without the caveat
    for doc in ("final-report.md", "demo-runbook.md"):
        text = (DOCS / doc).read_text()
        if "3.6" in text:
            assert re.search(
                r"reference|best[- ]scoring|best arm|never optimis", text
            ), f"{doc} quotes 3.6 without saying it is the reference arm"


def test_held_out_is_lower_than_train_sampled():
    """The honest number must stay the lower one -- that is the whole point."""
    c = load("guide_test_holdout_eval.json")["train_vs_test_comparison"]
    held = c["test_holdout_15000"]["accuracy"]
    train = c["train_sampled_999_rf_primary_pipeline"]["accuracy"]
    assert round(held, 4) == 0.6998
    assert round(train, 4) == 0.7347
    assert held < train


def test_injection_benchmark_composition():
    """400 attacks across 7 families, plus 100 real controls."""
    fam = load("m3_1_benchmark_generation.json")["family_counts"]
    attacks = {k: v for k, v in fam.items() if k.startswith("F")}
    assert sum(attacks.values()) == 400, attacks
    assert len(attacks) == 7
    assert fam["BCONTROL"] == 100


@pytest.mark.parametrize(
    "key, tpr, source",
    [
        ("h1", 0.0275, "m3_2_heuristic_detectors.json"),
        ("h2", 0.1050, "m3_2_heuristic_detectors.json"),
        ("h3", 0.9125, "m3_2_heuristic_detectors.json"),
        ("h_union", 0.9675, "m3_2_heuristic_detectors.json"),
        ("l1", 0.0325, "m3_2_learned_detectors.json"),
        ("l2", 0.3125, "m3_2_learned_detectors.json"),
        ("l4", 0.5899, "m3_2_learned_detectors.json"),
    ],
)
def test_detector_recalls_match_the_reported_table(key, tpr, source):
    assert round(load(source)[key]["overall_tpr"], 4) == tpr


def test_l3_is_reported_as_not_run_never_as_zero():
    l3 = load("m3_2_learned_detectors.json")["l3"]
    assert l3["status"] == "blocked"
    assert "overall_tpr" not in l3, "a blocked detector must not carry a score"


def test_paired_control_numbers():
    """The LLM scored below the majority-class floor on identical alerts."""
    c = load("rf_vs_llm_control.json")
    rf = round(c["randomforest"]["accuracy"], 4)
    llm = round(c["llm"]["accuracy"], 4)
    assert rf == 0.6555 and llm == 0.2823
    assert llm < 0.4928 < rf, "the LLM must stay below the constant-answer floor"


def test_explanation_node_cannot_change_a_verdict():
    v = load("verdict_invariance.json")
    assert v["verdicts_identical"] is True
    assert v["n_mismatches"] == 0
    assert v["n_scored"] == 999


def test_demo_script_form_values_are_the_ones_that_hold_for_review():
    """The runbook must not tell the presenter to narrate a hold using values
    that are auto-accepted through the web form."""
    text = (DOCS / "demo-runbook.md").read_text()
    assert "CredentialAccess" in text and "T1110;T1110.003" in text
    # the Collection/T1078 pair scores 0.2056 through the form -> auto-accepted
    assert "0.2056" in text, "the auto-accepted contrast must stay documented"
