# M4.3 PART A — explanation-quality human study, design record

Issue #40. This records what the package *is*, the two places it departs from a
literal reading of the issue, and the two limitations a reader of the eventual
result needs in front of them. Written before any rating happened, so none of it
is a post-hoc rationalisation of a number.

## The package

| file | what it is |
|---|---|
| `experiments/m4_3_build_human_study_package.py` | builds everything below, in three stages |
| `experiments/results/m4_3_study_alerts.csv` | the 100 sampled alerts, full GUIDE rows, with each one's RF verdict/probability/margin |
| `experiments/results/m4_3_explanations.json` | variant Y per alert, from the real A4 graph |
| `experiments/results/m4_3_rating_sheet_rater{A..E}.csv` | five blinded sheets, 200 rows each |
| `experiments/results/.m4_3_variant_key.csv` | the A/B → baseline/proposed mapping. **Withheld from raters.** |
| `docs/m4-3-rater-instructions.md` | the packet that goes to raters: task, 4 dimensions, 5-point anchors, edge cases |
| `tests/test_m4_3_rating_sheets.py` | asserts the blinding and the sheet contract on every build |

Sampling is seeded (`SEED = 42`). Stage 2 is the only stage that calls a model,
and it checkpoints after every alert, so a quota stall resumes rather than
re-spending the calls already made.

Variant Y is produced by invoking `build_triage_graph("rf_primary")` — the
deployed pipeline, MITRE enrichment and guardrails included — not by
re-implementing its prompt. What raters score is what the system actually emits.

All five sheets carry identical items in identical order; they differ only in the
pre-filled `rater` column. Fleiss' κ needs every rater scoring the same item, so
the A/B randomisation is shared across raters rather than drawn per rater.

## Two departures from the issue text

**1. The sample is deduplicated on displayed evidence.** `build_context()` puts
six low-cardinality fields in front of the model. A plain stratified draw of 100
GUIDE rows therefore collapsed to **57 distinct rating tasks** — one field
combination accounted for 16 of the 100 alerts, so a rater would have scored
identical text 16 times. That inflates Fleiss' κ, because a rater trivially
agrees with themselves and with everyone else on identical input, and it makes
the 100 "paired" Wilcoxon observations non-independent at an effective n of ~57.

GUIDE_Test contains 47,415 distinct combinations of those six fields, so
requiring 100 of them strains nothing. The sample is now deduplicated on
`EVIDENCE_COLUMNS` before stratification. Strata are unchanged: TP=34, BP=33,
FP=33 on `IncidentGrade`.

**2. The classifier sees the full GUIDE row, not the six displayed fields.**
An earlier build passed only the displayed evidence to the graph. The deployed
pipeline classifies the whole row, and the subset predicted differently on
**34 of 100** alerts — raters would have been shown `assigned_verdict=FalsePositive`
above an explanation of a BenignPositive verdict, and marked a third of the
corpus down for unfaithfulness that was ours and not the model's. Stage 3 now
refuses to build the sheets if the sampled verdict and the explained verdict
disagree on any alert.

## Two limitations to carry into the result

**1. The arms are not indistinguishable, and cannot be made so.** Issue #40
defines variant X as `Alert <ID> classified as <LABEL>.` — one line, no evidence,
no reasoning — against variant Y's 2–3 sentences of grounded prose. Shuffling
stops the two being presented as an explicit side-by-side, but any reader can
tell which is which immediately. The Wilcoxon result is therefore close to
predetermined on `analyst_usefulness`, and what it establishes is that the
proposed explanation beats having *no* explanation. That is a floor, not
evidence that it beats a reasonable alternative.

The informative comparison would set Y against the deterministic template the
pipeline already emits (`classify_with_rf`'s `reasoning`: verdict, probability,
decision margin against the review threshold, and the count of populated
evidence fields). That is a change to the study design and has not been made
unilaterally.

This is the same shape of problem as the M3.1 benchmark's "contains prose"
separator (`docs/m3-1-kappa-results.md`): a high agreement number that certifies
the labels are unambiguous and nothing stronger.

**2. The deduplicated sample is not representative of deployed accuracy.**
Dropping repeated field combinations removes the high-frequency rows the
classifier is most accurate on, leaving rarer combinations where it falls back
toward the majority class. On this sample the RF scores **0.42** accuracy and
assigns BenignPositive to **79 of 100** alerts, against **0.6998** on the
published balanced 15K held-out set.

This does not invalidate the study — a faithful, correct, useful explanation of a
*wrong* verdict still scores well on all four dimensions, and explanation quality
is what is being measured. But it does mean the sample is not a picture of
deployed behaviour, and that four fifths of the rated explanations explain the
same verdict class. Stratifying additionally on the RF verdict would spread that
out; it is a further departure from the issue text and is left as a decision for
review before the sheets are distributed.

## What is deliberately absent

Fleiss' κ, the Wilcoxon paired test, and PART B's Spearman cross-validation
against the automated proxies. No ratings exist. A scoring script that can run
before its input arrives is a script that can manufacture a number — the same
reason `m3_1_interrater_kappa.py` refuses to score one rater against themselves.
Scoring is written when the completed sheets come back.
