"""Tests for src/integrations/wazuh_adapter.py (week 10).

Confirms Wazuh-origin alerts, once mapped, flow cleanly through the
existing schema guardrail (src/agent/schema_guardrail.py) without any
changes to the guardrail itself -- proving the adapter, not the pipeline,
is what needs to change to support a new alert source.
"""

from src.agent.schema_guardrail import validate_field_types
from src.integrations.wazuh_adapter import wazuh_alert_to_raw_alert

SSH_BRUTE_FORCE_ALERT = {
    "timestamp": "2025-06-01T12:34:56.789+0000",
    "rule": {
        "id": 5710,
        "level": 10,
        "description": "sshd: brute force trying to get access to the system.",
        "groups": ["syslog", "sshd", "authentication_failed"],
        "mitre": {
            "id": ["T1110"],
            "tactic": ["Credential Access"],
            "technique": ["Brute Force"],
        },
    },
    "agent": {"id": "001", "name": "web-server-01"},
}

NO_MITRE_ALERT = {
    "timestamp": "2025-06-02T03:15:00.000+0000",
    "rule": {
        "id": 100100,
        "level": 3,
        "description": "PAM: Login session opened.",
        "groups": ["pam", "syslog"],
    },
    "agent": {"id": "002", "name": "db-server-01"},
}


def test_maps_ssh_brute_force_alert():
    raw_alert = wazuh_alert_to_raw_alert(SSH_BRUTE_FORCE_ALERT)

    assert raw_alert["AlertTitle"] == 5710
    assert raw_alert["DetectorId"] == 5710
    assert raw_alert["Category"] == "syslog, sshd, authentication_failed"
    assert raw_alert["MitreTechniques"] == "T1110"
    assert raw_alert["SuspicionLevel"] == "medium"
    assert raw_alert["Hour"] == 12
    assert raw_alert["DayOfWeek"] == 6  # 2025-06-01 is a Sunday


def test_maps_alert_with_no_mitre_mapping():
    raw_alert = wazuh_alert_to_raw_alert(NO_MITRE_ALERT)

    assert raw_alert["AlertTitle"] == 100100
    assert raw_alert["DetectorId"] == 100100
    assert raw_alert["MitreTechniques"] is None
    assert raw_alert["SuspicionLevel"] == "low"


def test_mapped_alerts_pass_schema_guardrail_unchanged():
    for wazuh_alert in (SSH_BRUTE_FORCE_ALERT, NO_MITRE_ALERT):
        raw_alert = wazuh_alert_to_raw_alert(wazuh_alert)
        assert validate_field_types(raw_alert) == []


def test_high_severity_bucket():
    high_severity_alert = {
        "timestamp": "2025-06-01T00:00:00.000+0000",
        "rule": {"id": 1, "level": 14, "groups": []},
    }
    raw_alert = wazuh_alert_to_raw_alert(high_severity_alert)
    assert raw_alert["SuspicionLevel"] == "high"
