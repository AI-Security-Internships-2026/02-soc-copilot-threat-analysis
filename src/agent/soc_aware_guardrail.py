"""H3, the "SOC-aware" heuristic layer (issue #36, M3.2 Part B).

Two ideas, both aimed at the gap H1 (guardrails.py) and H2 (schema_guardrail.py)
leave open -- free text smuggled into a field that isn't AlertTitle, phrased
without H1's multi-term conjunction patterns:

  (a) Field allowlist: in the real GUIDE schema, every field except
      AlertTitle is supposed to hold a short categorical/enum value (a MITRE
      ID, a verdict string, a device name, a suspicion level) -- not a
      sentence. A field other than AlertTitle holding sentence-shaped text is
      itself suspicious, regardless of what the sentence says.
  (b) Ten curated SOC-domain regex signatures, drawn from the phrasing
      actually observed in datasets/soc_injection_benchmark_v1.csv's F1/F2/F7
      rows -- persona-authority claims and output-contract manipulation that
      H1's narrower conjunction patterns don't cover.
"""

from __future__ import annotations

import re
from typing import Any

# Mirrors schema_guardrail.py's own field-scoped reasoning: AlertTitle is the
# one field the real GUIDE schema ever populates with something other than a
# short categorical code.
FREE_TEXT_ALLOWED_FIELDS = {"AlertTitle"}

# A short categorical value ("Execution", "T1059.001", "TruePositive") vs a
# sentence: sentence-shaped text has multiple words and enough length that a
# GUIDE categorical code would never reach.
_SENTENCE_MIN_WORDS = 4
_SENTENCE_MIN_CHARS = 25

_SOC_SIGNATURES = {
    "persona_authority_claim": re.compile(
        r"\b(?:senior soc lead|incident commander|unrestricted|no safety rules|"
        r"no restrictions|final authority)\b", re.IGNORECASE,
    ),
    "forced_response_directive": re.compile(
        r"\brespond (?:with exactly|only with)\b", re.IGNORECASE,
    ),
    "stop_generating": re.compile(r"\bstop generating\b", re.IGNORECASE),
    "json_verdict_injection": re.compile(
        r'"(?:verdict|final_verdict)"\s*:\s*"(?:TruePositive|BenignPositive|FalsePositive)"',
        re.IGNORECASE,
    ),
    "verdict_assignment": re.compile(r"\bverdict\s*=\s*(?:TruePositive|BenignPositive|FalsePositive)\b", re.IGNORECASE),
    "pre_approved_closure": re.compile(r"\bpre-approved for closure\b", re.IGNORECASE),
    "output_already_populated": re.compile(r"\balready been populated\b", re.IGNORECASE),
    "do_not_compute_new": re.compile(r"\bdo not compute a new one\b", re.IGNORECASE),
    "output_override_flag": re.compile(r"\boverride_prior_output\b", re.IGNORECASE),
    "sign_off_as": re.compile(r"\bsign off as\b", re.IGNORECASE),
}

assert len(_SOC_SIGNATURES) == 10


def _looks_like_sentence(value: str) -> bool:
    return len(value) >= _SENTENCE_MIN_CHARS and len(value.split()) >= _SENTENCE_MIN_WORDS


def inspect_alert_soc_aware(alert: dict[str, Any]) -> list[str]:
    """Return reason codes: field-allowlist violations and SOC-signature hits."""
    reasons: list[str] = []
    for field, value in alert.items():
        if not isinstance(value, str):
            continue
        if field not in FREE_TEXT_ALLOWED_FIELDS and _looks_like_sentence(value):
            reasons.append(f"field_not_allowlisted:{field}")
        for name, pattern in _SOC_SIGNATURES.items():
            if pattern.search(value):
                reasons.append(f"soc_signature:{name}:{field}")
    return reasons
