"""Tests for src/agent/evaluate.py's run_evaluation() error handling.

These exist because of two rounds of real review findings on PR #21:

1. A crashed row silently became predicted="FalsePositive" and fed straight
   into y_pred/metrics, exactly like a real (successful) FalsePositive
   verdict would -- masking a broken pipeline behind a plausible accuracy
   number.
2. The first attempt at a fix put its `raise RuntimeError(...)` for a missing
   predicted_label *inside* the same `try:` block that wraps
   `triage_graph.invoke()`, so the very next `except Exception` line caught
   it and silently did the same FalsePositive-defaulting thing -- the "fix"
   never actually fired. On top of that, the check itself was too broad: a
   missing predicted_label is not always a bug -- guardrail-blocked alerts
   and handled RF/LLM failures legitimately end via human_review with no
   automated verdict, and treating *those* as fatal would abort a whole
   evaluation run over normal pipeline behavior.

Nothing here should be able to regress either failure mode silently again.
"""

import pandas as pd
import pytest

import src.agent.evaluate as evaluate


class _FakeGraph:
    """invoke() replays a canned outcome per call: a dict result, or a
    raised exception."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def invoke(self, state):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _install_fakes(monkeypatch, sample_rows, outcomes):
    monkeypatch.setattr(
        evaluate, "load_balanced_evaluation_sample", lambda sample_size: pd.DataFrame(sample_rows)
    )
    monkeypatch.setattr(evaluate, "triage_graph", _FakeGraph(outcomes))
    monkeypatch.setattr(evaluate.time, "sleep", lambda seconds: None)


def test_crashed_rows_are_excluded_from_metrics_not_defaulted(monkeypatch, tmp_path):
    """A crashed row must not be silently scored as a fabricated FalsePositive
    prediction -- it must be excluded from accuracy/macro-F1 and counted in
    routing_summary.error_count instead."""
    _install_fakes(
        monkeypatch,
        sample_rows=[
            {"IncidentGrade": "TruePositive", "AlertTitle": 1},
            {"IncidentGrade": "TruePositive", "AlertTitle": 2},
            {"IncidentGrade": "BenignPositive", "AlertTitle": 3},
        ],
        outcomes=[
            {"predicted_label": "TruePositive", "triage_path": "llm"},
            RuntimeError("simulated agent crash"),
            {"predicted_label": "BenignPositive", "triage_path": "rf_fallback"},
        ],
    )

    output = evaluate.run_evaluation(sample_size=3, output_path=str(tmp_path / "out.json"))

    assert output["routing_summary"]["error_count"] == 1
    assert output["routing_summary"]["scored_count"] == 2
    # only the 2 successful rows should count toward accuracy -- if the crashed
    # row were still silently scored as FalsePositive, this would be off.
    assert output["accuracy"] == 1.0

    crashed_entries = [r for r in output["per_alert_results"] if r["triage_path"] == "error"]
    assert len(crashed_entries) == 1
    assert crashed_entries[0]["predicted"] is None
    assert "simulated agent crash" in crashed_entries[0]["error"]


def test_all_rows_crashing_raises_instead_of_reporting_metrics_from_nothing(monkeypatch, tmp_path):
    """A total pipeline failure must fail loud, not silently report metrics
    computed from zero successful predictions."""
    _install_fakes(
        monkeypatch,
        sample_rows=[
            {"IncidentGrade": "TruePositive", "AlertTitle": 1},
            {"IncidentGrade": "BenignPositive", "AlertTitle": 2},
        ],
        outcomes=[
            RuntimeError("simulated agent crash"),
            RuntimeError("simulated agent crash"),
        ],
    )

    with pytest.raises(RuntimeError, match="none of 2 rows produced a scorable prediction"):
        evaluate.run_evaluation(sample_size=2, output_path=str(tmp_path / "out.json"))


def test_dead_ended_graph_raises_instead_of_being_swallowed_by_its_own_except(monkeypatch, tmp_path):
    """Pins the PR #21 review finding: a state dict that comes back from a
    *successful* triage_graph.invoke() call (no exception raised) but has no
    predicted_label AND no needs_human_review flag is the Week 9 graph-wiring
    dead-end signature -- a node stopped early without reaching classification
    or human_review. This must actually raise and propagate out of
    run_evaluation, not be silently caught by the `except Exception` that
    guards the invoke() call (that except only wraps the `try`, not this
    `else`-clause check) and turned into a scored FalsePositive."""
    _install_fakes(
        monkeypatch,
        sample_rows=[
            {"IncidentGrade": "TruePositive", "AlertTitle": 1},
        ],
        outcomes=[
            # invoke() returns normally -- no exception -- but the state has
            # dead-ended before reaching parse_verdict or human_review_node.
            {"alert_context": "...", "mitre_context": "..."},
        ],
    )

    with pytest.raises(RuntimeError, match="likely a graph-wiring regression"):
        evaluate.run_evaluation(sample_size=1, output_path=str(tmp_path / "out.json"))


def test_guardrail_blocked_alert_does_not_raise_and_is_excluded_from_metrics(monkeypatch, tmp_path):
    """A legitimate no-verdict outcome (guardrail-blocked or a handled
    RF/LLM failure, both of which route through human_review_node and so
    always carry needs_human_review=True) must NOT be treated as a wiring
    regression -- it should be excluded from metrics via no_verdict_count,
    not abort the run."""
    _install_fakes(
        monkeypatch,
        sample_rows=[
            {"IncidentGrade": "TruePositive", "AlertTitle": 1},
            {"IncidentGrade": "BenignPositive", "AlertTitle": 2},
        ],
        outcomes=[
            {
                "guardrail_status": "blocked",
                "needs_human_review": True,
                "reasoning": "Input regex guardrail blocked LLM processing: prompt_injection",
            },
            {"predicted_label": "BenignPositive", "triage_path": "rf_fallback"},
        ],
    )

    output = evaluate.run_evaluation(sample_size=2, output_path=str(tmp_path / "out.json"))

    assert output["routing_summary"]["no_verdict_count"] == 1
    assert output["routing_summary"]["error_count"] == 0
    assert output["routing_summary"]["scored_count"] == 1
    no_verdict_entries = [r for r in output["per_alert_results"] if r["predicted"] is None]
    assert len(no_verdict_entries) == 1


def test_no_crashes_reports_zero_errors(monkeypatch, tmp_path):
    _install_fakes(
        monkeypatch,
        sample_rows=[
            {"IncidentGrade": "TruePositive", "AlertTitle": 1},
            {"IncidentGrade": "BenignPositive", "AlertTitle": 2},
        ],
        outcomes=[
            {"predicted_label": "TruePositive", "triage_path": "llm"},
            {"predicted_label": "BenignPositive", "triage_path": "rf_fallback"},
        ],
    )

    output = evaluate.run_evaluation(sample_size=2, output_path=str(tmp_path / "out.json"))

    assert output["routing_summary"]["error_count"] == 0
    assert output["routing_summary"]["scored_count"] == 2
