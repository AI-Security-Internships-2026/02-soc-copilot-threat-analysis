"""
Maps a Wazuh alert (its native JSON format, e.g. from alerts.json or the
Wazuh Indexer API) into this pipeline's `raw_alert` shape -- the same shape
`load_data.py` produces from GUIDE rows -- so Wazuh-origin alerts can flow
through the existing LangGraph triage pipeline unchanged.

Wazuh alert JSON reference (see docs/wazuh-integration.md for the full
field-by-field mapping rationale):
  {
    "timestamp": "2025-06-01T12:34:56.789+0000",
    "rule": {
      "id": 5710,
      "level": 10,
      "description": "sshd: brute force trying to get access to the system.",
      "groups": ["syslog", "sshd", "authentication_failed"],
      "mitre": {"id": ["T1110"], "tactic": ["Credential Access"], "technique": ["Brute Force"]}
    },
    "agent": {"id": "001", "name": "web-server-01"},
    ...
  }

Only `AlertTitle` and `DetectorId` need to be numeric (see
src/agent/schema_guardrail.py -- the issue #10 root cause was that GUIDE's
AlertTitle is a numeric ID, not text). Wazuh's `rule.id` is already numeric
and is the closest equivalent to both fields, since Wazuh doesn't separate
"alert title id" from "detector id" the way GUIDE's schema does.
"""

from typing import Any, Dict

import pandas as pd


def _suspicion_level(rule_level: int | None) -> str | None:
    """Buckets Wazuh's 0-15 rule.level into the low/medium/high scale
    `build_context` expects for SuspicionLevel."""
    if rule_level is None:
        return None
    if rule_level >= 12:
        return "high"
    if rule_level >= 7:
        return "medium"
    return "low"


def wazuh_alert_to_raw_alert(wazuh_alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts one Wazuh alert dict into the pipeline's raw_alert schema.

    LastVerdict is intentionally left unset -- it's GUIDE's historical
    analyst-assigned verdict field, which has no equivalent for a live,
    not-yet-triaged Wazuh alert.
    """
    rule = wazuh_alert.get("rule", {})
    mitre_ids = rule.get("mitre", {}).get("id", [])

    raw_alert: Dict[str, Any] = {
        "AlertTitle": rule.get("id"),
        "DetectorId": rule.get("id"),
        "Category": ", ".join(rule.get("groups", [])) or None,
        "MitreTechniques": ", ".join(mitre_ids) if mitre_ids else None,
        "SuspicionLevel": _suspicion_level(rule.get("level")),
    }

    timestamp = wazuh_alert.get("timestamp")
    if timestamp:
        ts = pd.Timestamp(timestamp)
        raw_alert["Hour"] = ts.hour
        raw_alert["DayOfWeek"] = ts.dayofweek

    return raw_alert
