"""Deterministic input checks applied before alert text reaches the LLM.

The GUIDE fields are normally structured data, but a production SOC pipeline can
receive untrusted free text (for example, an alert title supplied by an endpoint
or an analyst note).  This small, auditable guardrail detects common prompt
injection phrases and unexpectedly large fields.  A match is sent to human
review; it is never treated as a security verdict.
"""

from __future__ import annotations

import re
from typing import Any


MAX_FIELD_CHARS = 4_000
_INJECTION_PATTERNS = {
    "instruction_override": re.compile(
        r"\b(?:ignore|disregard|override)\b.{0,80}\b(?:previous|prior|above|system)\b.{0,80}\b(?:instruction|prompt|rule)s?\b",
        re.IGNORECASE | re.DOTALL,
    ),
    "system_prompt_reference": re.compile(r"\b(?:reveal|print|show|repeat)\b.{0,80}\b(?:system prompt|hidden prompt)\b", re.IGNORECASE | re.DOTALL),
    "role_impersonation": re.compile(r"\b(?:you are now|act as|role\s*:)\s*(?:a |an )?(?:system|assistant|developer|admin)\b", re.IGNORECASE),
    "jailbreak_keyword": re.compile(r"\b(?:jailbreak|do anything now|dan mode)\b", re.IGNORECASE),
}


def inspect_alert(alert: dict[str, Any]) -> list[str]:
    """Return stable reason codes for text that must not be passed to the LLM."""
    reasons: list[str] = []
    for field, value in alert.items():
        if not isinstance(value, str):
            continue
        if len(value) > MAX_FIELD_CHARS:
            reasons.append(f"oversize_field:{field}")
        for name, pattern in _INJECTION_PATTERNS.items():
            if pattern.search(value):
                reasons.append(f"{name}:{field}")
    return reasons

