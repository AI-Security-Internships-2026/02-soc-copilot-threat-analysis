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

## Known limitation, found during audit: the RF path is unvalidated for Wazuh alerts

The LLM/guardrail path is safe for Wazuh-origin alerts (verified above). The **RF fallback path is
not** — worth being explicit about this rather than letting it look more validated than it is.

`should_use_fallback()` routes any alert with fewer than 2 of `{MitreTechniques, SuspicionLevel,
LastVerdict}` populated to the trained Random Forest baseline instead of the LLM. Many real Wazuh
alerts will hit this (no MITRE mapping, no `LastVerdict` equivalent at all — see above). Checked
what actually happens: a Wazuh-mapped alert with only `SuspicionLevel` populated leaves 25 of the
RF model's 40 expected features as NaN (vs. GUIDE alerts, which are typically missing only a
handful of entity-specific evidence columns per alert). The call does **not** error —
scikit-learn 1.7's tree ensembles have built-in missing-value routing, so `predict_with_fallback()`
returns a normal-looking `(label, probability)` pair (verified: `BenignPositive`, 0.6, bucketed as
"medium confidence" by `classify_with_fallback`).

That's the concerning part: it fails *silently by looking fine*, not by erroring. The RF model has
never been trained or validated on this sparsity pattern — a Wazuh alert's ~62% feature-missing
rate is a different distribution than anything in GUIDE, where the model's missing-value handling
was learned. There's no evidence the resulting predictions are reliable, and no evidence they
aren't; it's genuinely unvalidated, not verified-bad.

**Recommendation, not yet implemented:** until there's labeled Wazuh data to check RF accuracy
against, treat any verdict on a Wazuh-origin alert as needing human review regardless of the
probability score, rather than trusting thresholds calibrated on GUIDE. Implementing that requires
tagging alerts with their origin through the pipeline state, which touches `graph.py`/`nodes.py`
routing — flagged here for a scoped follow-up rather than patched in passing.

### Week 15 update: this limitation got wider, not narrower

The paragraphs above were written when the RF was a *fallback*, reached only by alerts with fewer
than two populated evidence fields. Week 15 made the Random Forest the primary classifier: it now
assigns the verdict for **every** alert, and the LLM only writes the explanation
(`docs/weekly-progress.md` Week 15).

So the caveat no longer applies to a subset of Wazuh traffic — **it applies to all of it.** Every
Wazuh-origin alert now gets a verdict from a model trained solely on GUIDE, against a feature
vector roughly 62% missing, with no out-of-distribution check anywhere in the path. The failure
mode is unchanged and still the dangerous kind: it does not error, it returns a plausible label and
a plausible probability.

Two things partly offset this, and neither resolves it:

- The review gate is now keyed on the RF's **decision margin** (top-1 minus top-2 probability) at a
  0.20 threshold rather than on a bucketed probability. On GUIDE that margin is monotonically
  related to accuracy, so genuinely uncertain predictions are escalated. Whether that relationship
  survives a 62%-missing feature vector is exactly what has not been tested — an uncalibrated model
  can be confidently wrong, and margin is a calibration property.
- Wazuh alerts now also pass through the schema guardrail on `AlertTitle`/`DetectorId`, which the
  adapter populates from `rule.id`. That catches malformed input, not distribution shift.

**Revised recommendation.** An origin tag in `AlertState` and a hard "always review non-GUIDE
alerts" rule is now the minimum bar for running this pipeline against a live Wazuh feed, and it
should land before any deployment rather than after. The alternative — validating RF accuracy on
labelled Wazuh data — remains the better answer and still requires data that does not exist yet.
Until one of those happens, the honest description of Wazuh support is *a validated schema adapter
with an unvalidated classifier behind it*.

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

---

# Tier-1 schema-transfer measurement (Week 21, issue #43)

Source: `experiments/results/m5_3_wazuh_t1.json`, generated by
`experiments/m5_3_wazuh_t1_transfer.py`.

## Tier-1 vs Tier-2 — what the distinction means here

| Tier | What it measures | Needs | Status |
|---|---|---|---|
| **Tier-1** | Does the adapter preserve the information the classifier acts on? | Synthetic alerts only. No labels required. | **Done** |
| **Tier-2** | Is the classifier *accurate* on Wazuh alerts? | Real Wazuh alerts with analyst-assigned verdicts. | **Not done. No such data exists.** |

**The issue asked for a transfer-accuracy retention figure. That number is not
reported, because it would have been meaningless.** `src/data/generate_sample.py`
draws `IncidentGrade` with fixed weights, independently of every feature. The
experiment verifies this rather than asserting it: a 5-fold RandomForest scores
**0.3470** on the synthetic labels against a **0.4028** majority-class floor — it
cannot beat a constant answer, because there is nothing to learn. Both sides of
an accuracy comparison would therefore be chance, "retention" would land near
100%, and the ≥85% acceptance criterion would pass while measuring nothing. This
repository has already been caught by exactly that once:
`experiments/results/archive/agent_metrics.json` was withdrawn for being a
synthetic-data run whose labels are random noise.

## What was measured instead

The same synthetic incident is scored twice — once as a native GUIDE row, once
round-tripped GUIDE → Wazuh JSON → adapter → `raw_alert` — on matched
adapter-capable fields, so the only difference is the transformation itself.
Ground truth never enters.

| Measurement | Result (n=10,000) |
|---|---|
| **Verdict agreement, native vs round-tripped** | **0.9637** [0.9598, 0.9673] |
| Schema-guardrail pass rate on adapter output | 1.0000 |
| Pipeline completion rate (verdict produced, no error) | 1.0000 |
| Mean \|Δ\| in RF decision margin | 0.0722 (p95 0.1862) |

Field survival across the round trip: `AlertTitle`, `Category` and
`MitreTechniques` 100%; `DetectorId` 0.2%; `SuspicionLevel` 0%.

## Defect found: the SuspicionLevel vocabulary does not exist in the model

`_suspicion_level()` buckets Wazuh's `rule.level` into `low`/`medium`/`high`.
The deployed model's `SuspicionLevel` encoder knows only
`['Incriminated', 'Suspicious', 'nan']` — checked against **real** `GUIDE_Test.csv`,
so this is not an artefact of the synthetic generator's vocabulary. All three
adapter outputs therefore encode to **−1 (unknown)**.

Every Wazuh-origin alert loses its SuspicionLevel signal entirely — not
degraded, discarded. The field looks populated from end to end, which is why a
field-survival count alone would not have caught it; it took checking the value
against the encoder's classes.

**Fix:** map `rule.level` onto GUIDE's own vocabulary rather than a
low/medium/high scale the model was never trained on. Not applied here — it
changes deployed behaviour and belongs in its own reviewed change.

## Honest limitations

1. **Tier-1 only.** Every alert is synthetic and the labels are random and
   deliberately unused. This is a schema-transfer measurement, not an accuracy
   measurement, and 0.9637 is *agreement between two encodings of the same
   alert* — not accuracy on anything.
2. **No real Wazuh production data, labelled or otherwise, was available.**
   Tier-2 remains future work and no figure in this project stands in for it.
   Nothing here should be quoted as "Wazuh accuracy".
3. **Rule-ID semantic alignment was not attempted.** The adapter maps Wazuh
   `rule.id` into both `AlertTitle` and `DetectorId` because Wazuh does not
   separate them, so a Wazuh rule id and a GUIDE alert-title id sharing a value
   denote unrelated things. Verdict agreement measures whether the classifier
   sees the same *features*, not whether those features *mean* the same thing
   across domains. `DetectorId`'s 0.2% survival is this limitation showing up as
   a number, not a bug.
4. **`Category` is passed through, not manufactured.** It survives this round
   trip at 100% only because the Wazuh `rule.groups` were seeded from GUIDE
   categories. Real Wazuh traffic carries `syslog`/`sshd`/`authentication_failed`,
   none of which the encoder knows — so the practical Category loss on real
   alerts is not measured here and should not be inferred from the 100%.
