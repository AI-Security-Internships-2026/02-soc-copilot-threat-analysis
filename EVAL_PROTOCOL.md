# Evaluation Protocol

M2.3 PART A (issue #33). This document defines the three acceptable ways a
number in this project can be scored, and the rule for which numbers are
allowed to appear in the paper. It exists because M2.1 measured, precisely,
what happens when this isn't written down: the deployed baseline's published
headline accuracy (0.7718) was scored on a row-level split, and the same
model retrained with an incident-level split scores 2.83 points lower
(`experiments/results/grouped_split_baseline.json`, replicated across 5
seeds in `experiments/results/m2_1_splitmethod_delta_5seeds.json`); a
class-balanced sample drawn from rows an incident's sibling was already
trained on scores 24.3 points higher than a clean one
(`experiments/results/incident_leakage_audit.json`, replicated across 3 seeds
in `experiments/results/m2_1_leakage_300k_balanced.json`). Neither gap is a
bug in a specific script. Both are a property of *which rows ended up in the
holdout*, and every experiment script in this repository makes that choice
somewhere. This document is where that choice gets a name, so a reviewer (or
a future contributor) can tell which regime a number was measured under
without re-deriving it from the split code.

## 1. Background

GUIDE's label (`IncidentGrade`) is incident-level: it is constant across
every row belonging to one `(OrgId, IncidentId)` (verified at 100.0000% in
`incident_leakage_audit.json`'s Part A, 52,797/52,797 incidents in the
deployed model's training slice). A row-level `train_test_split` does not
know this, and routinely puts two rows of the same incident on opposite
sides of the split boundary. When it does, the holdout row's label was
recoverable from a labelled sibling the model already saw -- not from
anything the model learned about the alert itself. That is what M2.1
measures and what this protocol exists to stop from happening silently
again.

## 2. Three protocols

| Protocol | Mode | Split rule | Status |
|---|---|---|---|
| **A** | **PREFERRED** | Score on `datasets/GUIDE_Test.csv`, Kaggle's own held-out file, sampled with 0% row and 0% incident overlap against the training slice (verified per-sample in every score using `experiments/overlap_audit.py`). | The only regime a headline number should be reported under without a paired comparator. |
| **B** | **ACCEPTABLE** (for ablations) | `GroupShuffleSplit` on `(OrgId, IncidentId)`, internal to `GUIDE_train.csv`. No incident crosses the split boundary (assert `holdout_incident_leakage_rate == 0`). | Used where Protocol A's fixed 15,000-row sample doesn't give enough internal signal for an ablation or hyperparameter sweep -- M2.1 PART A, M2.4's `validate` mode, M2.3 PART B's internal train/val split. |
| **C** | **LAB_INFLATED** | Row-level `train_test_split` (stratified or plain) on `GUIDE_train.csv`. Rows of the same incident can and do land on both sides. | The deployed model's own training protocol (`src/models/baseline.py`) and every number measured under it before Week 17. **Never reported alone.** May appear only paired with its Protocol A or B counterpart, specifically to measure the inflation the split rule itself introduces (that pairing is M2.1's whole subject). |

## 3. Reproduction steps per mode

**Protocol A** -- score against the committed 15,000-row cache (or regenerate
it):
```
venv/bin/python experiments/guide_test_holdout_eval.py --sample-size 15000
```
Confirms 0% overlap itself, via the `unknown_category_diagnostic` block and
`experiments/overlap_audit.py`'s own standalone run:
```
venv/bin/python experiments/overlap_audit.py
```

**Protocol B** -- `GroupShuffleSplit(n_splits=1, test_size=0.2,
random_state=<seed>)` on `(OrgId, IncidentId)`, e.g.:
```
venv/bin/python experiments/grouped_split_baseline.py
venv/bin/python experiments/m2_1_splitmethod_5seeds.py
venv/bin/python experiments/m2_4_classifier_suite.py --mode validate
```
Every Protocol B script asserts `holdout_incident_leakage_rate == 0` (or the
equivalent zero-crossing check) on its own holdout before reporting a number.

**Protocol C** -- reproduces the deployed model's own training protocol,
only for paired comparison against A or B:
```
venv/bin/python experiments/grouped_split_baseline.py   # writes both C and B arms, paired
venv/bin/python experiments/incident_leakage_audit.py   # Part D: leaked (Protocol-C-shaped) vs clean buckets
```

## 4. Protocol compliance checklist

Before a number from a new experiment script is cited in a paper table or a
weekly-progress claim:

1. **Does the script's own output JSON carry a `"protocol"` field** with
   value `"PREFERRED"`, `"ACCEPTABLE"`, or `"LAB_INFLATED"`? If not, add one
   at the point the script writes its result -- not as a later retrofit.
   (`experiments/incident_leakage_audit.py`, `m2_1_splitmethod_5seeds.py`,
   `m2_1_historical_eval_overlap.py`, and `m2_4_classifier_suite.py` already
   do this.)
2. **If the protocol is C**, is the number paired with its A or B
   counterpart in the same table, with the gap stated? A bare Protocol C
   number with no comparator is not citable under this checklist, regardless
   of how the script itself is labelled.
3. **If the protocol is B**, does the script assert zero incident overlap
   across the split boundary rather than merely intend it? An assertion that
   can fail loudly is required, not a comment claiming the property holds.
4. **Does the citing text name the protocol**, e.g. "0.6998 (Protocol A,
   n=15,000)" rather than a bare number? A reader should not have to open the
   JSON to know which regime produced a figure.

Any result not citing Protocol A or B is lab-internal and excluded from
paper tables. Protocol C / LAB_INFLATED numbers may appear only in paired
comparison tables built specifically to measure the leakage magnitude the
split rule introduces -- never as a standalone headline figure.

## Authoritative replacement-number source

`docs/stale_claims_audit.md` (M1.2 PART A) is the audit that corrected every
numeric claim this repository carried before Week 17 against what was
actually measured. Where a number in an older document conflicts with a
number in this file's linked JSONs, the JSON -- and the protocol it's
tagged with -- is authoritative; `docs/stale_claims_audit.md` records why the
older prose was wrong, not a second source of truth.
