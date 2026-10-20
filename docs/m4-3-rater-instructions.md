# Rater instructions — SOC alert explanation quality pass

**You will need:** your own rating sheet (`m4_3_rating_sheet_raterA.csv` through
`...raterE.csv` — you get exactly one) and about 60–90 minutes.

Please do not discuss the items, your scores, or your reasoning with the other
raters until every sheet has been returned. Five people rating the same 200 rows
independently is the whole point; the agreement statistic is meaningless if the
scores influenced each other.

## What you are looking at

A SOC triage system reads the fields of a security alert, assigns a verdict
(`TruePositive`, `BenignPositive`, or `FalsePositive`), and then writes a short
written explanation of that verdict for the analyst who has to action it.

Each row of your sheet is **one such explanation**. You get:

| column | what it is |
|---|---|
| `alert_evidence` | every field the system had available, as `Field=value` pairs. This is the complete evidence — there is nothing else it could have known. |
| `assigned_verdict` | the verdict the system assigned. **Already decided.** |
| `explanation_text` | the explanation you are scoring. |

**You are not judging whether the verdict is right.** The verdict was assigned
by a separate classifier and is fixed. You are judging whether the *explanation*
is a faithful, correct, and useful account of it. An explanation of a verdict you
personally disagree with can still score 5 across the board.

Two different explanations were written for each alert, and your sheet contains
both, in shuffled order. You do not need to find them or compare them — score
every row on its own, against its own `alert_evidence`.

## How to fill in the sheet

Open the CSV in Excel or Google Sheets (File → Import → upload, "comma" as the
separator). For every row, put an integer **1–5** in each of the four score
columns:

`faithfulness`, `factual_correctness`, `analyst_usefulness`, `no_unsupported_claims`

Leave `rater`, `row_id`, `item_id`, `variant_shown`, `alert_evidence`,
`assigned_verdict` and `explanation_text` untouched — the scoring script joins on
`row_id`, so re-sorting rows is fine but renaming or deleting columns is not.

`rater_note` is optional and free-text. Use it for anything you found genuinely
ambiguous, or where you felt the anchors below did not fit what you were reading.
These notes are read: where raters disagree, the note is how we tell a real
judgement call from a gap in the rubric.

**Score every row on every dimension, including ones you are unsure about.**
There is no "unsure" or "N/A" option by design — the agreement statistic needs a
complete matrix. Put your hesitation in `rater_note` instead.

## The four dimensions

Score each independently. A row can be 5 on one and 1 on another; that is
expected and informative. Where a dimension genuinely does not apply — no
security terms appear at all, for instance — score what is there rather than
leaving it blank, and say so in `rater_note`.

### 1. `faithfulness` — does every claim trace to the evidence shown?

| | anchor |
|---|---|
| **1** | Contradicts the evidence. States something the `alert_evidence` shows to be false, or describes a verdict other than `assigned_verdict`. |
| **2** | Mostly untraceable. More of the explanation comes from nowhere than from the evidence. |
| **3** | Mixed. Some claims cite the evidence; at least one substantive claim does not. |
| **4** | Traceable with one minor stretch — an inference that is reasonable but not actually shown. |
| **5** | Every claim traces to a field in `alert_evidence`, or is explicitly flagged as an inference. |

### 2. `factual_correctness` — are the security terms right?

Covers MITRE ATT&CK technique IDs and names, attack-category names, product and
telemetry terminology.

| | anchor |
|---|---|
| **1** | Wrong. A T-code is paired with the wrong technique name, or a category is plainly misdescribed. |
| **2** | One clear error plus further imprecision. |
| **3** | One clear error, or several loose usages, in otherwise correct text. |
| **4** | Correct but imprecise — right concept, informal or incomplete naming. |
| **5** | Every security term used is correct, and used in the right sense. |

### 3. `analyst_usefulness` — would this save you time on shift?

| | anchor |
|---|---|
| **1** | No time saved. Tells you nothing you could not read off the alert yourself. |
| **2** | Marginal. You would rewrite it before putting it in a ticket. |
| **3** | A usable starting point needing real editing. |
| **4** | Nearly ticket-ready; small edits only. |
| **5** | SOC-ready as written. You would paste it into the ticket unedited. |

### 4. `no_unsupported_claims` — hallucination count

Count distinct assertions of fact that the evidence neither states nor supports.
A hedged statement ("this may indicate…") is not a hallucination; an invented
specific ("the host contacted 10.2.3.4") is, even if plausible.

| | anchor |
|---|---|
| **1** | Two or more unsupported claims. |
| **2** | One unsupported claim that materially affects how an analyst would act. |
| **3** | One unsupported claim of minor consequence. |
| **4** | No invented facts, but one assertion stated more confidently than the evidence warrants. |
| **5** | Zero. Nothing asserted beyond what the evidence supports. |

## Edge cases

- **Very short explanations.** Length is not a dimension. A one-sentence
  explanation that is faithful, correct, and makes no unsupported claims scores
  5/5/·/5 — score `analyst_usefulness` on whether it actually helps, not on
  whether it is brief.
- **"The evidence is thin."** An explanation that says the verdict rests on a
  weak signal is being faithful, not unhelpful. Reward it on dimensions 1 and 4.
- **Fields absent from `alert_evidence`.** Only what is listed was available.
  An explanation that discusses a field not listed is making an unsupported
  claim, however reasonable it sounds.
- **Empty `MitreTechniques`.** Roughly half these alerts have no MITRE technique.
  An explanation that names one anyway is hallucinating; one that notes the
  absence is being faithful.

## Returning your sheet

Save as CSV with `_completed` appended to the filename — e.g.
`m4_3_rating_sheet_raterA_completed.csv` — and send it back. The scoring step
looks for exactly that name.

No personal information is stored. Sheets are identified only by the rater
letter already filled into your `rater` column, and only that letter appears in
any committed result.
