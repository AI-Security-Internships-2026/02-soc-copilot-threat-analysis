# Decision memo: `LastVerdict` and `SuspicionLevel` in the feature matrix

**M1.2 Part C2 (issue #30) · 2026-09-06 · branch `asma-week-17-verification`**
**Evidence:** `experiments/results/field_inclusion_audit.json`, produced by
`experiments/field_inclusion_audit.py`.

---

## The question

`LastVerdict` and `SuspicionLevel` are Microsoft-product verdicts about the same
alert the classifier is grading. The Limitations sections have flagged them as
target-adjacent — plausibly leaky — since Week 12. Nobody had checked two things:
whether they are actually in the deployed feature matrix, and what they are worth
if they are.

## What was found

**They are in the matrix.** The deployed `baseline_model.joblib` uses 40
features, and both are among them. So the concern was live, not hypothetical.

**They are worth almost nothing.** Two Random Forests were trained on the same
100,000-row slice — one with all 40 features, one with those two dropped — and
both scored on the held-out `GUIDE_Test.csv` sample (n=15,000), the only split
where the answer is not itself distorted by incident-level leakage:

| arm | features | accuracy | macro F1 |
|---|---|---|---|
| with `LastVerdict` + `SuspicionLevel` | 40 | 0.7147 | 0.7100 |
| without them | 38 | 0.7125 | 0.7080 |
| **difference** | | **+0.0022** | **+0.0020** |

**Two tenths of an accuracy point.** For comparison, incident-level label leakage
is worth **+24.3 points** — two orders of magnitude larger. Whatever is wrong
with this project's evaluation, these two fields are not it.

## Decision: **(a) keep, and document as analyst-derived**

Rejecting (b) *ablate and deploy*: removing them costs 0.2 points for no
measurable integrity gain, and would invalidate every published number — the
209-alert control, the McNemar result, the ablation arms, the leakage audit —
for a change the evidence says does not matter.

Rejecting (c) *document as leaky-but-known*: that was the previous state, and it
overstates the problem. Calling a 0.2-point contribution "leakage" alongside a
24.3-point effect misleads a reader about where the real risk is.

**What "analyst-derived" means, and the caveat that stays.** These fields are
real inputs available at triage time in a production SOC — a Tier-1 analyst sees
the product's prior verdict before grading an alert, so a model that uses it is
modelling the deployment, not cheating. The honest caveat is narrower than
"leaky": in a SOC whose upstream product does *not* populate these fields, the
model loses about 0.2 points, and that is now measured rather than guessed.

## Related finding (Part C1)

`DetectorId` is **not** in the feature matrix, but the schema guardrail treats it
as a numeric ID and blocks alerts whose value is non-numeric. Across 500,000
rows: `DetectorId` has **4,559 distinct values, 0 non-numeric**; `AlertTitle` has
**33,042 distinct values, 0 non-numeric**. The guardrail's assumption holds, so
it produces no false blocks on real GUIDE traffic. Pinned by
`tests/test_schema_guardrail.py::test_detector_id_and_alert_title_are_numeric_across_a_large_sample`.

## Reproduce

```bash
venv/bin/python experiments/field_inclusion_audit.py                  # both parts, ~10 min
venv/bin/python experiments/field_inclusion_audit.py --skip-ablation  # Part C1 only, ~1 min
```

## Caveat on the ablation arms

Both arms are retrained with `n_estimators=200, random_state=42` and default
class weighting, which is *not* identical to the deployed model's configuration —
so 0.7147 is not the deployed 0.6998, and should not be quoted as it. The arms
are identical to each other in everything except the two dropped columns, which
is what makes the **difference** meaningful. Only the difference should be cited.
