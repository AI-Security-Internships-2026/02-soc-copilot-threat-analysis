"""Issue #42 PART A: the consolidated 5-config ablation must stay true to its
sources, and the interpretation doc must stay true to the consolidation.

The failure mode worth guarding is not arithmetic -- it is a number drifting out
of the prose while the artifact moves on, which is what put a stale 56-cell
count in six files and a 321/500 coverage figure in the datasheet.
"""

import json
import re
from pathlib import Path

import pytest

RESULTS = Path("experiments/results")
CONSOLIDATED = RESULTS / "m5_1_ablation_consolidated.json"
ABLATION = RESULTS / "m5_1_ablation_5config.json"
BURDEN = RESULTS / "m5_1_burden_sweep.json"
DOC = Path("docs/m5-1-ablation-interpretation.md")

requires_consolidated = pytest.mark.skipif(
    not CONSOLIDATED.exists(),
    reason="m5_1_ablation_consolidated.json not generated -- run experiments/m5_1_consolidate_ablation.py",
)

EXPECTED_CONFIGS = ["full", "no_llm_explanation", "nomitre", "noguardrails", "nohitl"]


@requires_consolidated
def test_five_configurations_present_in_order():
    data = json.loads(CONSOLIDATED.read_text())
    assert [c["config"] for c in data["configs"]] == EXPECTED_CONFIGS


@requires_consolidated
def test_every_delta_accuracy_is_exactly_zero():
    """Not 'within tolerance'. The architecture makes it exact, and a nonzero
    value here means a component reached the verdict path -- which would be a
    real finding, not a rounding artifact."""
    data = json.loads(CONSOLIDATED.read_text())
    for config in data["configs"]:
        assert config["delta_acc_vs_full"] == 0.0, f"{config['config']} moved accuracy"


@requires_consolidated
def test_label_identity_backs_the_zero_deltas():
    ablation = json.loads(ABLATION.read_text())
    for name, block in ablation["label_identity_vs_full"].items():
        assert block["labels_identical_to_full"] is True, name
        assert block["n_label_differences"] == 0, name


@requires_consolidated
def test_nohitl_still_agrees_with_the_burden_sweep_t0_row():
    """Mati's #42 item 2. Two independent runs of the same configuration."""
    data = json.loads(CONSOLIDATED.read_text())
    check = data["nohitl_vs_burden_sweep_t0"]
    assert check["agrees"] is True, check

    burden = json.loads(BURDEN.read_text())
    sweep = burden.get("sweep") or burden.get("rows")
    t0 = next(r for r in sweep if r["T"] == 0.0)
    nohitl = next(c for c in data["configs"] if c["config"] == "nohitl")
    assert nohitl["accuracy"] == t0["auto_accepted_accuracy"]
    assert nohitl["auto_accept_pct"] == t0["auto_accepted_pct"] == 1.0


@requires_consolidated
def test_only_hitl_and_guardrails_move_their_own_axis():
    """The components differ on exactly the axes they own, and nowhere else."""
    configs = {c["config"]: c for c in json.loads(CONSOLIDATED.read_text())["configs"]}
    full = configs["full"]

    assert configs["nohitl"]["auto_accept_pct"] == 1.0
    assert configs["noguardrails"]["guardrail_attack_tpr"] == 0.0
    assert full["guardrail_attack_tpr"] > 0.0
    for name in ("no_llm_explanation", "nomitre", "noguardrails"):
        assert configs[name]["auto_accept_pct"] == full["auto_accept_pct"], name
    for name in ("no_llm_explanation", "nomitre", "nohitl"):
        assert configs[name]["guardrail_attack_tpr"] == full["guardrail_attack_tpr"], name


@requires_consolidated
def test_the_contaminated_999_figure_is_not_in_the_accuracy_column():
    """0.7347 is GUIDE_train-sampled and incident-level contaminated. It may be
    cross-referenced in prose but must never sit in an accuracy cell beside the
    held-out 0.6998."""
    data = json.loads(CONSOLIDATED.read_text())
    for config in data["configs"]:
        assert config["accuracy"] != 0.7347, config["config"]
        assert "guide_test_balanced" in config["evaluation_set"]


@requires_consolidated
@pytest.mark.skipif(not DOC.exists(), reason="interpretation doc not written")
def test_interpretation_doc_quotes_the_artifact_it_is_built_from():
    """Every headline number in the prose must still appear in the artifacts."""
    doc = DOC.read_text()
    data = json.loads(CONSOLIDATED.read_text())
    ablation = json.loads(ABLATION.read_text())
    full = next(c for c in data["configs"] if c["config"] == "full")

    for value in (f"{full['accuracy']}", f"{full['macro_f1']}"):
        assert value in doc, f"{value} missing from the interpretation doc"

    explanation = ablation["explanation_study"]
    assert str(explanation["full"]["d1_grounded_rate"]) in doc
    assert str(explanation["nomitre"]["d1_grounded_rate"]) in doc
    assert str(explanation["significance"]["d1_groundedness"]["fisher_exact_p"]) in doc

    blocked = ablation["guardrail_tpr"]["full"]["blocked"]
    assert re.search(rf"\b{blocked}\b", doc), f"blocked count {blocked} missing"

    # The prediction that was NOT met must stay recorded as not met.
    assert explanation["significance"]["d1_groundedness"]["prediction_met"] is False
    assert "not met" in doc
