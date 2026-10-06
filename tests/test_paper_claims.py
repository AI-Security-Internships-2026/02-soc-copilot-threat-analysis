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


# ===================================================================
# Category 7 — architecture ablations (M5.1 PART A, issue #42)
# ===================================================================

def test_no_ablation_changes_a_single_verdict():
    """The strongest form of the architecture claim, and the one worth pinning.

    classify_with_rf reads raw_alert directly -- not the built context, not
    mitre_context -- so disabling enrichment, the guardrails, or the review gate
    must not move ANY label. Exact element-wise identity over 15,000 alerts, not
    'accuracy within a tolerance', because a tolerance would hide compensating
    errors.
    """
    ident = load("m5_1_ablation_5config.json")["label_identity_vs_full"]
    for config in ("nomitre", "noguardrails", "nohitl"):
        assert ident[config]["labels_identical_to_full"] is True, config
        assert ident[config]["n_label_differences"] == 0, (
            f"{config} moved {ident[config]['n_label_differences']} labels; "
            "the classifier is reading something it should not")


def test_ablations_reproduce_the_published_held_out_accuracy():
    cfgs = load("m5_1_ablation_5config.json")["configs"]
    for name, c in cfgs.items():
        assert abs(c["accuracy"] - 0.6998) <= 1e-3, (name, c["accuracy"])
        assert c["n_errors"] == 0, name


def test_disabling_the_gate_auto_accepts_everything():
    """nohitl is the one ablation that must change something observable."""
    cfgs = load("m5_1_ablation_5config.json")["configs"]
    assert cfgs["nohitl"]["auto_accept_pct"] == 1.0
    assert cfgs["full"]["auto_accept_pct"] < 1.0
    # and it must agree with the M5.1 PART B sweep at T=0
    t0 = next(r for r in load("m5_1_burden_sweep.json")["sweep"] if r["T"] == 0.0)
    assert t0["auto_accepted_pct"] == cfgs["nohitl"]["auto_accept_pct"]


def test_removing_guardrails_drops_attack_detection_to_zero():
    g = load("m5_1_ablation_5config.json")["guardrail_tpr"]
    assert g["noguardrails"]["tpr"] == 0.0
    assert g["full"]["tpr"] > 0.0
    # H1 union H2 must lie between the published components and their sum
    h = load("m3_2_heuristic_detectors.json")
    h1, h2 = h["h1"]["overall_tpr"], h["h2"]["overall_tpr"]
    assert max(h1, h2) <= g["full"]["tpr"] <= min(1.0, h1 + h2)


def test_mitre_ablation_result_is_reported_with_its_non_confirmation():
    """Issue #42 predicted D1 groundedness would drop >=10 points. It dropped 8,
    which is significant but smaller than predicted; D2 dropped more than 10 but
    is not significant at n=55. Neither prediction fully confirms, and the
    artifact must keep saying so rather than rounding toward the hypothesis."""
    sig = load("m5_1_ablation_5config.json")["explanation_study"]["significance"]
    d1, d2 = sig["d1_groundedness"], sig["d2_mitre_match"]
    assert d1["significant_at_0_05"] is True and d1["prediction_met"] is False
    assert d2["prediction_met"] is True and d2["significant_at_0_05"] is False
    assert d1["full"] > d1["nomitre"] and d2["full"] > d2["nomitre"]


# ===================================================================
# Category 8 — the deployed operating threshold (issue #30)
# ===================================================================

def test_deployed_threshold_matches_the_documented_decision():
    from config.config import HITL_AUTO_ACCEPT_MARGIN, HITL_THRESHOLD_DECISION
    assert HITL_AUTO_ACCEPT_MARGIN == 0.20
    assert "0.12 is not adopted" in HITL_THRESHOLD_DECISION


def test_020_is_the_smallest_threshold_clearing_the_train_sampled_claim():
    """The anchor the paper's justification rests on. If a future re-run moves
    the sweep so that a different T is the smallest one whose CI clears the
    train-sampled figure, the paper's argument for 0.20 no longer holds and
    must be rewritten -- not silently left in place."""
    train_sampled = load("large_train_sampled_rf_eval.json")["train_sampled"]["accuracy"]
    rows = sorted(load("m5_1_burden_sweep.json")["sweep"], key=lambda r: r["T"])
    clearing = [r["T"] for r in rows
                if r["auto_accepted_accuracy_ci"][0] > train_sampled]
    assert clearing, "no threshold clears the train-sampled figure at 95%"
    assert min(clearing) == 0.20, (
        f"smallest clearing threshold is {min(clearing)}, not 0.20; the paper's "
        "justification in Section 4.15 needs revisiting")


def test_no_pareto_knee_exists_in_the_burden_sweep():
    """The paper states plainly that marginal efficiency is flat and there is no
    optimum. Guard the claim: if a pronounced knee ever appears, the honest
    framing changes from 'policy choice' to 'tuned value'."""
    rows = sorted(load("m5_1_burden_sweep.json")["sweep"], key=lambda r: r["T"])
    effs = []
    for prev, cur in zip(rows, rows[1:]):
        d_burden = cur["escalated_pct"] - prev["escalated_pct"]
        if d_burden > 0:
            effs.append((cur["auto_accepted_accuracy"]
                         - prev["auto_accepted_accuracy"]) / d_burden)
    assert effs
    assert max(effs) / min(effs) < 2.0, (
        f"marginal efficiency now spans {min(effs):.3f}-{max(effs):.3f}; that is "
        "no longer 'flat' and Section 4.15's argument needs rewriting")


# ===================================================================
# Category 9 — the overlap-correlation null (issue #31)
# ===================================================================

def test_overlap_correlation_null_is_reported_not_tuned():
    """Issue #31 is explicit that the r>=0.90 expectation must not be chased.
    Guard that the null stays reported as measured."""
    d = load("m2_1_overlap_correlation_analysis.json")
    assert d["n_observations"] == 4
    assert abs(d["pearson"]["r"] - 0.1139) < 1e-3
    assert d["pearson"]["p_value"] > 0.05
    assert d["expected_min_r_not_met_and_not_pursued"]["expected"] == 0.9


def test_overlap_correlation_is_unidentified_not_merely_weak():
    """The finding that matters: one observation swings r across its full range,
    so neither sign is supportable."""
    loo = load("m2_1_overlap_correlation_analysis.json")["leave_one_out"]
    rs = [e["r"] for e in loo]
    assert max(rs) > 0.9 and min(rs) < -0.9, rs


def test_control_209_composition_confound_is_recorded():
    """The 209-alert control differs from every other set on class balance and
    difficulty, not on overlap. If that stops being true the paragraph in §4.12
    is wrong."""
    prof = load("m2_1_overlap_correlation_analysis.json")["set_profiles"]
    c, parent = prof["control_209"], prof["train_sampled_999"]
    assert parent["majority_class_floor"] == pytest.approx(1 / 3, abs=1e-3)
    assert c["majority_class_floor"] > 0.45          # 0.4928 — a different baseline
    assert c["rf_margin_mean"] < parent["rf_margin_mean"]   # genuinely harder
    assert c["accuracy"] < parent["accuracy"]              # despite shared leakage


# ===================================================================
# Category 10 — external reproduction and task formulation (issue #32)
# ===================================================================

def test_external_deltas_are_reported_as_measured_not_tuned():
    """Issue #32 is explicit that +0.020 must not be targeted. The two external
    results are below it and must stay reported that way."""
    d = load("m2_2_task_formulation_check.json")
    ext = d["external_comparators"]
    assert ext["kaggle_notebook_1_catboost"]["delta_acc"] == 0.007
    assert ext["kaggle_notebook_2_randomforest"]["delta_acc"] == 0.0092
    note = d["no_tuning_note"].lower()
    assert "tuned" in note and "0.020" in note, note


def test_binarising_reduces_but_does_not_close_the_delta_gap():
    """The finding: formulation explains part of the gap, not all of it. If a
    future run shows binarising closing it entirely, §4.12's conclusion changes."""
    cells = load("m2_2_task_formulation_check.json")["cells"]
    for rows in (100000, 300000):
        three = cells[f"three_class@{rows}"]["delta_acc"]
        binary = cells[f"binary@{rows}"]["delta_acc"]
        assert binary < three, f"binarising did not reduce the delta at {rows}"
    # at the row count matching the notebooks, a clear residual remains
    assert cells["binary@300000"]["delta_acc"] > 2 * 0.0081, (
        "our binary delta now matches the external mean; the paper's 'does not "
        "explain all of it' claim no longer holds")


def test_more_rows_raises_leakage_and_the_delta():
    """Counter-intuitive and load-bearing: sample size moves the wrong way to
    explain the gap."""
    cells = load("m2_2_task_formulation_check.json")["cells"]
    small, large = cells["three_class@100000"], cells["three_class@300000"]
    assert large["delta_acc"] > small["delta_acc"]
    assert (large["row_level"]["holdout_incident_leakage_rate"]
            > small["row_level"]["holdout_incident_leakage_rate"])


def test_the_50_upvote_criterion_is_unsatisfiable_and_verified():
    """Issue #32 asks why no >=50-upvote notebook was used. Re-verified live
    against the Kaggle API rather than carried over as an assertion."""
    v = load("m2_2_task_formulation_check.json")["kaggle_vote_count_reverification"]
    assert v["notebooks_clearing_50_votes"] == 0
    assert v["top_vote_count"] == 39
    assert v["requirement_satisfiable"] is False
