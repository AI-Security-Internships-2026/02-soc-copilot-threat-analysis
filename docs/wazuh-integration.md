# Wazuh Integration Research (Week 10)

## What Wazuh is

[Wazuh](https://wazuh.com/) is an open-source SIEM/XDR platform, shipped as four components:

| Component | Role |
|---|---|
| Agent | Runs on monitored endpoints, forwards logs/events to the server |
| Server | Collects agent events, applies decoders + rules, generates alerts |
| Indexer | Stores and indexes alerts (built on OpenSearch) |
| Dashboard | Web UI for browsing alerts, dashboards, CIS-benchmark compliance checks |

2025 saw active releases (4.11.x, 4.12.0), and it's one of the most widely deployed open-source
SIEM/XDR platforms — a real, live alert source, unlike GUIDE, which is a static 2024 Kaggle
snapshot with no ongoing stream.

## Why it's relevant here

Everything this pipeline currently evaluates against comes from one static, already-labeled
dataset (GUIDE). Wazuh represents the other end of the spectrum: a live rule engine producing
alerts continuously, with its own alert schema, no pre-existing `IncidentGrade` label, and no
guarantee that its `AlertTitle`-equivalent field is even structured the same way GUIDE's is.
Testing the pipeline's guardrails and triage logic against a second, structurally different alert
source is a stronger validation of the design than only ever testing against GUIDE rows.

This is also directly precedented in the literature — see `docs/literature-review.md` Paper 6
("Enhancing Security Operations Center: Wazuh Security Event Response with RAG-Driven Copilot",
MDPI *Sensors* 2025), which builds essentially the same LLM+RAG-over-alerts architecture as this
project, but grounded in Wazuh instead of a static dataset.

## Wazuh's alert JSON schema

A Wazuh alert (from `alerts.json` or the Indexer API) looks like:

```json
{
  "timestamp": "2025-06-01T12:34:56.789+0000",
  "rule": {
    "id": 5710,
    "level": 10,
    "description": "sshd: brute force trying to get access to the system.",
    "groups": ["syslog", "sshd", "authentication_failed"],
    "mitre": {
      "id": ["T1110"],
      "tactic": ["Credential Access"],
      "technique": ["Brute Force"]
    }
  },
  "agent": {"id": "001", "name": "web-server-01"},
  "data": { "...": "decoder-specific fields, vary by log source" }
}
```

Key differences from GUIDE that shaped the adapter design:
- **`rule.id`** is Wazuh's numeric rule identifier — the closest equivalent to both GUIDE's
  `AlertTitle` and `DetectorId`, both of which the issue #10 investigation found are numeric ID
  fields, not free text (see `src/agent/schema_guardrail.py`'s docstring for that root-cause
  writeup). Wazuh doesn't separate these two concepts the way GUIDE's schema happens to, so both
  fields map to the same `rule.id`.
- **`rule.mitre.id`** maps directly onto `MitreTechniques` — Wazuh ships MITRE ATT&CK mappings
  for a large subset of its default ruleset, so this reuses `src/agent/mitre_lookup.py` unchanged.
- **`rule.groups`** (Wazuh's own alert categorization, e.g. `sshd`, `authentication_failed`) maps
  onto `Category`.
- **`rule.level`** (0–15 severity) is bucketed into `SuspicionLevel` (`low`/`medium`/`high`) to
  match the categorical scale `build_context` expects.
- There is no Wazuh equivalent of `LastVerdict` — that field is GUIDE's *historical, analyst-
  assigned* verdict, which doesn't exist for a live, not-yet-triaged alert. It's left unset.

## What was built this week

`src/integrations/wazuh_adapter.py`: a pure mapping function,
`wazuh_alert_to_raw_alert(wazuh_alert: dict) -> dict`, translating one Wazuh alert JSON dict into
this pipeline's `raw_alert` shape — the same shape `src/data/load_data.py` produces from GUIDE
rows. No changes were needed to `src/agent/graph.py`, `nodes.py`, or either guardrail: a mapped
Wazuh alert was smoke-tested through `apply_regex_guardrail` → `apply_schema_guardrail` →
`build_context` directly and passed both guardrails cleanly, producing a normal context block for
the LLM/RF routing stage. `tests/test_wazuh_adapter.py` covers the mapping (including the
severity-bucketing and missing-MITRE cases) and asserts mapped output passes
`validate_field_types()` unchanged.

## What full integration would require (future work, not done this week)

This week's work is a schema adapter validated against realistic *sample* Wazuh alert JSON, not
a live deployment. Standing up an actual Wazuh instance is a real infrastructure task:

1. A Docker Compose single-node stack (indexer + server + dashboard containers).
2. At least one enrolled agent (or the built-in log-collection/vulnerability-detection modules)
   generating real alerts instead of hand-written samples.
3. A polling or webhook mechanism pulling from the Wazuh Indexer API into this pipeline, rather
   than the one-alert-at-a-time adapter call used for the prototype/tests.
4. Deciding whether Wazuh-origin alerts get evaluated separately from GUIDE (different schema,
   different label availability — there's no ground-truth `IncidentGrade` for a live alert) or
   folded into the same `evaluate.py` harness with a human-in-the-loop labeling step.

This is scoped out for now given the size of the remaining Sep 8 writeup timeline (see the updated
`README.md` roadmap) — flagged here as a concrete next step rather than started speculatively.
