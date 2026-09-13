# M2.3 deploy decision: ADOPT vs KEEP

**Issue #33 (M2.3 PART B). Decision: KEEP the current `baseline_model.joblib`
for the remainder of M2–M5; revisit at M6 as a single, deliberate swap
bundled with the final pre-submission reproducibility pass — not a mid-
milestone change.** The evidence for adopting is real and quantified below,
not dismissed; the reason to defer is sequencing, not doubt about the
number.

## What was measured

`experiments/m2_3_deploy_grouped_model.py` retrained M2.4's selected model
(M3a — plain RandomForestClassifier(200), LabelEncoder categoricals; M2.4
found it beat every alternative among 7 classifier families, including
CatBoost/XGBoost/LightGBM/one-hot-RF/LLM-only) on 500,000 rows — 5x the
deployed model's 100,000 — via `GroupShuffleSplit` on `(OrgId, IncidentId)`,
Protocol B, with **0 incidents crossing the train/val boundary (verified,
not assumed)**. Re-scored on the exact samples the paper already reports on:

| Sample | Deployed (100K rows, Protocol C) | Candidate (500K rows, Protocol B) | Delta |
|---|---|---|---|
| GUIDE_Test held-out, n=15,000 (Protocol A) | 0.6998 | 0.7294 | **+0.0296** |
| A4-pipeline sample, n=999 | 0.7347 | 0.7978 | **+0.0631** |

Full numbers: `experiments/results/m2_3_grouped_deployed.json`. The
candidate artifact is compatible with the deployed inference path without a
wrapper (`deploy_compatible: true`) and is saved to
`models/best_grouped_classifier.joblib` — **not** written over
`experiments/results/baseline_model.joblib`. No deployed path, no
downstream experiment, and no already-published number changed by running
this script.

## Why this isn't a small effect to wave off

Two things distinguish this from the "not yet" call recorded in
`docs/weekly-progress.md:2489-2491` after Week 17:

1. **It's now measured, not projected.** That entry cited the
   classifier-improvement study's internal-holdout estimate; this is the
   same architecture, more data, a verified-clean external split, scored on
   the paper's own reference samples.
2. **The gain is larger on the harder, more analyst-relevant sample.**
   +2.96 points on the balanced clean held-out set, +6.31 points on the
   evidence-rich A4-pipeline sample — the FalsePositive class (the weakest,
   per every prior recall breakdown in this repo) still trails at 0.561/0.667
   recall respectively, so this is not a free lunch, but it's a genuine,
   reproducible improvement from more training data and a correct split, not
   a different architecture or added complexity.

## Why KEEP now anyway

Adopting mid-M2 would not just swap one number — `baseline_model.joblib` is
read by `src/agent/fallback_classifier.py`'s inference path, which every
subsequent experiment in this project's remaining schedule (M3's guardrail
benchmark, M4's security-integrity ASR runner, M5's ablations and cost
breakdown) will build on. Swapping now means:

- Every M1-era published number in `docs/final-report.md` (already drafted,
  22-page Elsevier target) that cites 0.6998/0.7347/the control-node
  arm results would need re-measuring and re-writing, mid-schedule, with
  M3–M6 (issues #35–#47, due through Sep 20) not yet started.
- M4.1's per-family ASR stats and M5.1's ablation Pareto curve would be
  computed against a model that didn't exist when M2.4 selected it as best
  — a different provenance story than "we measured 7 classifiers, picked the
  best, then scaled it up once, deliberately, at the point every other
  number was final."

Swapping is real, welcome work — just work with one clean landing point, not
a moving target across 5 more milestones. **M6 (issue #47, the manuscript
draft) is that point**: bundling the swap with the final reproducibility
pass means every number in the submitted paper is computed against the same
final model exactly once, rather than some sections citing the 100K-row
baseline and others citing a mid-schedule replacement.

## What would change this call

If M3 or M4's guardrail/integrity work turns out to depend on classifier
accuracy in a way that's materially affected by a 3-6 point RF accuracy gap
(e.g. a detector-benchmark false-negative rate that's sensitive to exactly
this), that dependency would move this decision earlier, not later. Nothing
measured so far indicates that; noted here so the next person revisiting this
doesn't have to re-derive the condition under which KEEP stops being right.

## What's already in place for the eventual ADOPT

- `models/best_grouped_classifier.joblib` is a real, scored, ready artifact
  right now — adopting later is "point `MODEL_PATH` at it and re-run the
  affected regression tests," not a from-scratch retrain.
- `EVAL_PROTOCOL.md` (M2.3 PART A) already defines the Protocol A/B/C
  labelling this swap's numbers are reported under, so the M6 changeover
  doesn't also have to invent that documentation under deadline pressure.
