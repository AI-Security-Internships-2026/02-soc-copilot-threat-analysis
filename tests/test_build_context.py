"""Tests for src/agent/nodes.py's build_context().

Exists because of a real Week 12 finding: build_context() used bare
truthiness (`if alert.get(field):`) to decide whether to include a field.
GUIDE alerts loaded via pandas represent a missing MitreTechniques/
SuspicionLevel/LastVerdict as float('nan'), and bool(float('nan')) is True
in Python -- so a missing field wasn't skipped, it was rendered as the
literal text "MITRE Technique: nan" / "Suspicion Level: nan" in the prompt
sent to the LLM. Measured against the alerts the pipeline actually routes to
the LLM (evidence_field_count >= 2), this hit 55% of them for
MitreTechniques and 31% for SuspicionLevel (experiments/llm_subset_eval.py).
"""

from src.agent.nodes import build_context


def test_nan_fields_are_omitted_not_rendered_as_the_string_nan():
    state = {
        "raw_alert": {
            "AlertTitle": 2,
            "Category": "CommandAndControl",
            "MitreTechniques": float("nan"),
            "DetectorId": 2,
            "SuspicionLevel": float("nan"),
            "LastVerdict": "Suspicious",
        }
    }

    context = build_context(state)["alert_context"]

    assert "nan" not in context.lower()
    assert "MITRE Technique" not in context
    assert "Suspicion Level" not in context
    assert "Last Verdict: Suspicious" in context


def test_populated_fields_still_render_normally():
    state = {
        "raw_alert": {
            "AlertTitle": 15723,
            "Category": "Collection",
            "MitreTechniques": "T1078;T1078.004",
            "DetectorId": 5,
            "SuspicionLevel": "Suspicious",
            "LastVerdict": "Malicious",
        }
    }

    context = build_context(state)["alert_context"]

    assert "Alert Title: 15723" in context
    assert "Category: Collection" in context
    assert "MITRE Technique: T1078;T1078.004" in context
    assert "Detector: 5" in context
    assert "Suspicion Level: Suspicious" in context
    assert "Last Verdict: Malicious" in context


def test_all_fields_missing_falls_back_to_placeholder():
    state = {"raw_alert": {}}

    context = build_context(state)["alert_context"]

    assert context == "No alert details available."
