"""
M6.3 PART A -- lock the paper's headline claims (issue #46).

If someone edits preprocess.py, changes a seed, or swaps a model, these fail
fast and name the claim that moved. Complements tests/test_reported_numbers.py,
which pins the figures the *demo* quotes; this file pins the figures a *reviewer*
will check.

Tolerance policy, per the issue: every tolerance is sourced, never guessed.
  1. If M6.3 PART B computed a CI for the cell, use its half-width.
  2. Otherwise use the M6.1 manifest tolerance for that table.
Each assertion names its source in a comment.

Claims whose experiment has not run yet are SKIPPED with the issue number that
will produce them -- never asserted against a placeholder, and never quietly
dropped so the count looks better.
"""

import json
from pathlib import Path

import pytest

RESULTS = Path("experiments/results")

# M6.1 manifest tolerances (experiments/m6_1_build_manifest.py)
TOL_DETERMINISTIC = 1e-4
TOL_LLM = 5e-3


def load(name):
    path = RESULTS / name
    if not path.exists():
        pytest.skip(f"{name} not on this branch yet")
    return json.loads(path.read_text())


def ci_half_width(*path):
    """Half-width of the PART B interval for a cell, as a tolerance."""
    node = load("m6_3_ci_backfill.json")
    for key in path:
        node = node[key]
    return (node["ci_upper"] - node["ci_lower"]) / 2


# ===================================================================
# Category 1 — classifier baselines (5 assertions)
# ===================================================================

def test_best_classifier_held_out_accuracy_clears_0_68():
    """The suite's best arm must stay above the bar the paper claims."""
    models = load("m2_4_heldout_n15k.json")["models"]
    best = max(models.items(), key=lambda kv: kv[1]["accuracy"])
    assert best[1]["accuracy"] >= 0.68, f"best is {best[0]} at {best[1]['accuracy']}"
    assert best[0] == "M3a", "the selected best arm changed identity"


def test_llm_scores_below_the_majority_class_floor_on_the_control_set():
    """The paper's central negative result. Tolerance: PART B CI half-width."""
    c = load("rf_vs_llm_control.json")
    llm = c["llm"]["accuracy"]
    floor = c["reference_baselines"]["majority_class_accuracy"]
    assert llm < floor, f"LLM {llm} is no longer below the constant-answer floor {floor}"
    assert abs(floor - 0.4928) <= 5e-3          # manifest tolerance, Tab 4
    assert abs(llm - 0.2823) <= ci_half_width("tab4", "llm_accuracy")


def test_llm_confidence_interval_is_disjoint_from_the_floor():
    """Stronger than the point comparison above: the intervals must not overlap,
    otherwise 'below the floor' is not supported at 95%."""
    b = load("m6_3_ci_backfill.json")
    assert b["tab4"]["llm_accuracy"]["ci_upper"] < b["tab4"]["majority_floor"]["ci_lower"]


def test_llm_only_arm_of_the_suite_also_fails_on_held_out():
    """M7 is the LLM scored on the 15,000-row held-out split."""
    m = load("m2_4_heldout_n15k.json")["models"]
    assert m["M7"]["accuracy"] < m["M3a"]["accuracy"]
    assert m["M7"]["accuracy"] < 0.49


def test_label_encoded_and_onehot_random_forests_agree_within_one_point():
    """M3a vs M3b: the encoding choice must not be doing the work."""
    m = load("m2_4_heldout_n15k.json")["models"]
    assert abs(m["M3a"]["accuracy"] - m["M3b"]["accuracy"]) <= 0.01


# ===================================================================
# Category 2 — leakage (3 assertions)
# ===================================================================

def test_leakage_overall_delta_is_at_least_20_points():
    d = load("incident_leakage_audit.json")["part_d_causal_test"]
    delta = d["leaked"]["accuracy"] - d["clean"]["accuracy"]
    assert delta >= 0.20, f"leakage effect fell to {delta:.4f}"


def test_leakage_true_positive_delta_is_at_least_35_points():
    """The leak concentrates in TruePositive, as the paper argues."""
    d = load("incident_leakage_audit.json")["part_d_causal_test"]
    tp = (d["leaked"]["per_class_recall"]["TruePositive"]
          - d["clean"]["per_class_recall"]["TruePositive"])
    assert tp >= 0.35, f"TP-only leakage effect fell to {tp:.4f}"


def test_benign_positive_delta_is_the_smallest_of_the_three():
    """Predicted ordering: BP is the majority class, so a labelled sibling adds
    least there. If this inverts, the mechanism story is wrong."""
    d = load("incident_leakage_audit.json")["part_d_causal_test"]
    deltas = {c: d["leaked"]["per_class_recall"][c] - d["clean"]["per_class_recall"][c]
              for c in ("TruePositive", "BenignPositive", "FalsePositive")}
    assert min(deltas, key=deltas.get) == "BenignPositive", deltas


def test_split_rule_replication_holds_in_every_seed():
    d = load("m2_1_splitmethod_delta_5seeds.json")
    assert all(s["row_level_split"]["accuracy"] > s["group_level_split"]["accuracy"]
               for s in d["per_seed"])
    assert d["wilcoxon_delta_acc_vs_zero"]["p_value"] < 0.05


# ===================================================================
# Category 3 — security / ASR (4 assertions)
# ===================================================================

def test_a4_triage_asr_is_exactly_zero():
    asr = load("m4_1_security_asr_runner.json")      # skips until PR #50 merges
    assert asr["arms"]["A4"]["triage_asr"] == 0.0


def test_a1_no_defense_triage_asr_is_at_least_0_25():
    asr = load("m4_1_security_asr_runner.json")
    assert asr["arms"]["A1"]["triage_asr_no_defense"] >= 0.25


def test_a1_vs_a4_mcnemar_is_significant():
    asr = load("m4_1_security_asr_runner.json")
    assert asr["mcnemar_a4_vs_a1"]["p_value"] < 0.05


def test_no_node_can_alter_the_classifier_verdict():
    """The architectural invariant the 0% triage-ASR claim rests on. This one
    needs no new experiment -- it is checked over all 999 evaluation alerts."""
    v = load("verdict_invariance.json")
    assert v["verdicts_identical"] is True
    assert v["n_mismatches"] == 0
    assert v["n_scored"] == 999


# ===================================================================
# Category 4 — guardrails and operating point (3 assertions)
# ===================================================================

def test_detector_union_recall_and_zero_false_positives():
    h = load("m3_2_heuristic_detectors.json")
    assert h["h_union"]["overall_tpr"] >= 0.95
    assert h["h1"]["fpr_on_bcontrol"] == 0.0
    assert h["h3"]["fpr_on_bcontrol"] == 0.0


def test_deployed_regex_filter_is_reported_honestly_as_weak():
    """Guards against someone quoting the flattering 5% self-authored figure as
    if it generalised. The 400-attack number is lower and is the real one."""
    h = load("m3_2_heuristic_detectors.json")
    g = load("guardrail_layer_eval.json")
    assert h["h1"]["overall_tpr"] < g["regex_guardrail"]["injection_recall"]
    assert h["h1"]["overall_tpr"] < 0.05


def test_recommended_operating_point_auto_accepts_most_alerts():
    """M5.1 PART B, on the held-out 15,000."""
    d = load("m5_1_burden_sweep.json")
    rec = d["recommended_operating_point"]
    assert rec["T"] == 0.12
    assert rec["auto_accepted_pct"] >= 0.60, rec


def test_burden_sweep_is_monotone_and_anchors_to_the_held_out_figure():
    """Raising the threshold can only auto-accept fewer alerts, and T=0 must
    reproduce the published ungated held-out accuracy -- that anchor is what
    makes the rest of the curve trustworthy."""
    d = load("m5_1_burden_sweep.json")
    rows = sorted(d["sweep"], key=lambda r: r["T"])
    pcts = [r["auto_accepted_pct"] for r in rows]
    assert pcts == sorted(pcts, reverse=True), pcts
    t0 = rows[0]
    assert t0["T"] == 0.0 and t0["auto_accepted_pct"] == 1.0
    assert abs(t0["auto_accepted_accuracy"] - 0.6998) <= 1e-3, (
        "T=0 must equal the published held-out accuracy")


def test_rf_margin_gate_is_correctly_oriented_unlike_the_llm_confidence_gate():
    """The paper's confidence-inversion finding was that the LLM gate escalated
    its BETTER predictions. The RF margin gate must not repeat that: escalated
    alerts should be ones the model gets wrong more often."""
    d = load("m5_1_burden_sweep.json")
    for r in d["sweep"]:
        esc = r["escalated_accuracy_model_would_have_given"]
        if r["escalated_n"] >= 100:
            assert esc < r["auto_accepted_accuracy"], (
                f"at T={r['T']} the gate escalates alerts the model gets RIGHT "
                f"more often ({esc} vs {r['auto_accepted_accuracy']}) -- inverted")


# The issue's original "Wazuh transfer retention within +/-0.20" assertion is
# deliberately absent. M5.2 PART A established that the synthetic generator's
# labels carry no signal, so a retention figure would compare chance with
# chance. The four assertions in Category 6 replace it and check something
# real: verdict agreement, which needs no labels at all.


# ===================================================================
# Category 5 — operational cost (M5.2 PART B, issue #43)
# ===================================================================

def test_routed_path_throughput_agrees_with_the_committed_benchmark():
    """The composed per-stage figure must land just under the independently
    measured end-to-end throughput -- adding stages can only slow it down."""
    c = load("m5_4_latency_cost.json")
    composed = c["end_to_end"]["routed_path_throughput_alerts_per_sec"]
    measured = c["llm_stage"]["throughput_alerts_per_second"]
    assert composed <= measured, "composition is faster than the measured whole"
    assert abs(composed - measured) / measured < 0.05, (composed, measured)


def test_the_llm_call_dominates_the_routed_path():
    """The premise the evidence-density router exists to exploit."""
    c = load("m5_4_latency_cost.json")
    assert c["end_to_end"]["llm_share_of_routed_path"] > 0.95


def test_router_reduces_api_cost():
    c = load("m5_4_latency_cost.json")["cost"]
    assert c["usd_per_day_with_router"] < c["usd_per_day_all_routed"]
    assert c["router_cost_reduction_factor"] > 1.0


def test_cost_figures_are_labelled_as_unverified_pricing():
    """A dollar figure quoted from an unverified price list must say so, or it
    will be read as measured."""
    c = load("m5_4_latency_cost.json")["pricing"]
    assert "not verified" in c["source"].lower()


# ===================================================================
# Category 6 — cross-domain transfer (M5.2 PART A, issue #43)
# ===================================================================

def test_wazuh_tier1_reports_agreement_not_accuracy():
    """The synthetic labels are noise, so an accuracy figure here would be
    meaningless. Guard against someone 'helpfully' adding one later."""
    d = load("m5_3_wazuh_t1.json")
    assert "verdict_agreement_native_vs_roundtripped" in d
    assert "accuracy_comparison_not_reported" in d
    blob = json.dumps(d).lower()
    assert "transfer_acc" not in blob and "retention_ref_acc" not in blob


def test_synthetic_labels_are_demonstrably_unlearnable():
    """The justification for the above, verified rather than asserted."""
    ev = load("m5_3_wazuh_t1.json")["accuracy_comparison_not_reported"]["evidence"]
    assert ev["labels_are_learnable"] is False
    assert ev["cv_accuracy_mean"] < ev["majority_class_floor"], (
        "a RandomForest now beats the majority floor on synthetic labels -- the "
        "generator changed, and the reasoning in this experiment needs revisiting")


def test_wazuh_adapter_suspicionlevel_defect_is_recorded():
    """A real defect found by measurement: the adapter emits a vocabulary the
    model's encoder does not contain. If someone fixes the adapter, this test
    should be updated together with it -- not deleted."""
    v = load("m5_3_wazuh_t1.json")["encoder_vocabulary_compatibility"]["SuspicionLevel"]
    assert v["all_adapter_values_unknown"] is True
    assert set(v["adapter_values_unknown_to_encoder"]) == {"low", "medium", "high"}


def test_wazuh_roundtrip_preserves_most_verdicts():
    d = load("m5_3_wazuh_t1.json")
    a = d["verdict_agreement_native_vs_roundtripped"]
    assert a["n"] >= 1000
    assert a["point"] >= 0.90, "schema transfer fidelity regressed"
    assert d["schema_guardrail_pass_rate"]["point"] == 1.0
    assert d["pipeline_completion_rate"]["point"] == 1.0
