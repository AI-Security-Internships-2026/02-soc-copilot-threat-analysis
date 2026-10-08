"""Issue #39: a rate-limited row must stay retryable.

The control-node ablation is paced across quota days with --daily-call-budget.
That only works if a row the budget could not afford is retried next time. Until
2026-10-06 a transient HTTP 429 was written into the checkpoint exactly like a
real result, so arm (d) exhausted its quota at row 230, cached 110 rate-limit
failures, and any resume would have skipped them forever -- permanently
reporting 120/299 as though the model, not the budget, had produced it.
"""

import json
from pathlib import Path

import pytest

from experiments.control_node_ablation import _is_transient_failure, _load_checkpoint


def test_rate_limit_failures_are_retryable():
    for message in (
        "LLM call failed after 5 attempts: Error code: 429 - rate limit reached",
        "Rate limit reached for model",
        "quota exceeded",
        "tokens per day (TPD) limit",
    ):
        assert _is_transient_failure({"predicted_label": None, "error": message}), message


def test_real_failures_and_real_results_are_not_retryable():
    """A model that answered, or that failed for its own reasons, is done.
    Retrying either would re-spend quota or loop forever."""
    assert not _is_transient_failure({"predicted_label": "TruePositive", "error": None})
    assert not _is_transient_failure({"predicted_label": None, "error": "unparseable response: ''"})
    assert not _is_transient_failure({"predicted_label": None, "error": None})
    # A 429 that nonetheless produced a verdict is a result, not a failure.
    assert not _is_transient_failure({"predicted_label": "BenignPositive", "error": "429 retried ok"})


def test_loading_a_poisoned_checkpoint_drops_the_rate_limited_rows(tmp_path, monkeypatch):
    import experiments.control_node_ablation as mod

    path = tmp_path / "arm_z.jsonl"
    records = [
        {"_row_index": 0, "predicted_label": "TruePositive", "error": None},
        {"_row_index": 1, "predicted_label": None,
         "error": "LLM call failed after 5 attempts: Error code: 429 - rate limit"},
        {"_row_index": 2, "predicted_label": None, "error": "unparseable response: ''"},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    monkeypatch.setattr(mod, "_checkpoint_path", lambda arm: path)

    done = _load_checkpoint("z")
    assert set(done) == {0, 2}, "the 429 row must be retried; the other two must not"


@pytest.mark.skipif(
    not Path("experiments/results/.control_node_ablation_checkpoints/arm_d.jsonl").exists(),
    reason="arm (d) checkpoint not present -- run experiments/control_node_ablation.py",
)
def test_arm_d_checkpoint_reports_only_genuinely_scored_rows():
    """Guards the specific artifact #39 reports coverage from."""
    path = Path("experiments/results/.control_node_ablation_checkpoints/arm_d.jsonl")
    written = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    done = _load_checkpoint("d")
    assert len(done) <= len(written)
    assert all(not _is_transient_failure(r) for r in done.values())
