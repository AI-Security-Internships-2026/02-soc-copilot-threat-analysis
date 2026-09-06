"""The human-review gate depends on the classifier's margin and nothing else.

M1.2 Part B (issue #30). Week 15 measured the LLM's self-reported confidence as
*inversely* calibrated on the 209-alert control set: alerts it labelled "high"
scored 0.256, alerts it labelled "medium" scored 0.383. A review gate keyed on
that string therefore auto-accepted the model's least reliable predictions --
the safety net was inverted, and nothing in the pipeline would have said so.

The fix was to gate on the Random Forest's decision margin, which is monotonic
in accuracy. These tests are what stops that fix from being quietly undone: they
assert the property directly rather than trusting the current shape of the code.

The third test is the important one. It runs the same alert twice, changing only
the LLM's self-reported confidence, and asserts the routing decision is
identical -- i.e. that the confidence string has no causal influence on the
outcome at all, only on what is displayed.
"""

import pytest

from config.config import HITL_AUTO_ACCEPT_MARGIN, T_init
from src.agent.nodes import RF_REVIEW_MARGIN_THRESHOLD, route_after_rf_verdict

ACCEPT = "end"
ESCALATE = "human_review"


def state(margin, confidence=None, label="TruePositive", error=None):
    """A minimal post-classification state, as route_after_rf_verdict sees it."""
    s = {"predicted_label": label, "rf_margin": margin}
    if confidence is not None:
        s["confidence"] = confidence
    if error is not None:
        s["error"] = error
    return s


def test_config_threshold_is_the_deployed_threshold():
    """The gate uses the documented constant, not a second copy of the number."""
    assert RF_REVIEW_MARGIN_THRESHOLD == HITL_AUTO_ACCEPT_MARGIN == T_init == 0.20


# --- 1. high margin wins even when the LLM says it is unsure -----------------
def test_high_margin_with_low_llm_confidence_is_accepted():
    assert route_after_rf_verdict(state(0.85, confidence="low")) == ACCEPT


# --- 2. low margin escalates even when the LLM says it is certain ------------
def test_low_margin_with_high_llm_confidence_is_escalated():
    assert route_after_rf_verdict(state(0.01, confidence="high")) == ESCALATE


# --- 3. the confidence string has no causal effect on routing ----------------
@pytest.mark.parametrize(
    "margin", [0.0, 0.05, 0.10, 0.15, 0.19, 0.20, 0.21, 0.30, 0.60, 1.0]
)
def test_swapping_llm_confidence_never_changes_the_decision(margin):
    """Identical alerts, opposite self-reported confidence, same outcome.

    This is the invariant the whole architecture rests on. If it ever fails,
    the LLM has regained influence over a triage outcome.
    """
    decisions = {
        route_after_rf_verdict(state(margin, confidence=c))
        for c in ("high", "medium", "low", "", None)
    }
    assert len(decisions) == 1, (
        f"at margin {margin} the routing decision depended on the LLM's "
        f"self-reported confidence: {decisions}"
    )


# --- 4. a threshold of 0.00 accepts everything that has a verdict ------------
def test_threshold_zero_accepts_every_scored_alert(monkeypatch):
    monkeypatch.setattr("src.agent.nodes.RF_REVIEW_MARGIN_THRESHOLD", 0.00)
    margins = [0.0, 0.01, 0.2, 0.5, 1.0]
    assert [route_after_rf_verdict(state(m)) for m in margins] == [ACCEPT] * len(margins)


# --- 5. a threshold of 1.00 escalates everything below a perfect margin ------
def test_threshold_one_escalates_everything_short_of_certainty(monkeypatch):
    monkeypatch.setattr("src.agent.nodes.RF_REVIEW_MARGIN_THRESHOLD", 1.00)
    margins = [0.0, 0.2, 0.5, 0.9, 0.999]
    assert [route_after_rf_verdict(state(m)) for m in margins] == [ESCALATE] * len(margins)


# --- failure paths always reach a human -------------------------------------
def test_an_alert_with_no_verdict_is_escalated_whatever_the_margin():
    assert route_after_rf_verdict(state(0.99, label=None)) == ESCALATE


def test_an_errored_alert_is_escalated_whatever_the_margin():
    assert route_after_rf_verdict(state(0.99, error="RF classifier failed")) == ESCALATE


def test_a_missing_margin_is_escalated_rather_than_assumed_safe():
    assert route_after_rf_verdict({"predicted_label": "TruePositive"}) == ESCALATE


# --- the boundary is inclusive, and stated ----------------------------------
def test_the_threshold_itself_is_accepted():
    """`margin >= threshold` accepts. Pinned so the comparison cannot flip."""
    assert route_after_rf_verdict(state(HITL_AUTO_ACCEPT_MARGIN)) == ACCEPT
    assert route_after_rf_verdict(state(HITL_AUTO_ACCEPT_MARGIN - 1e-9)) == ESCALATE


# --- the deployed graph must not route on confidence anywhere ---------------
def test_the_deployed_graph_has_no_confidence_based_routing():
    """Static guard over the rf_primary graph's routing function.

    `route_after_verdict` (which does branch on the confidence string) belongs
    to the retired legacy_hybrid graph and is kept only so the published
    ablation arm stays reproducible. The deployed path must never acquire one.
    """
    import inspect

    source = inspect.getsource(route_after_rf_verdict)
    assert "confidence" not in source, (
        "route_after_rf_verdict now reads a confidence value; the human-review "
        "gate must depend on the classifier margin alone."
    )
