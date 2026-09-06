# Demo Runbook

Every command below was run end to end and produced the output shown. Run them
in order. Total time: **about 6 minutes**, or 3 if you skip the optional steps.

Read `docs/project-explained.md` first — this runbook assumes you know what the
numbers mean.

**Setup, once, before the meeting:**

```bash
cd "/Users/asma/Desktop/iot lab/02-soc-copilot-threat-analysis"
git checkout asma-week-15
```

Everything runs from the repository root. All commands use `venv/bin/python`
so no environment activation is needed.

---

## Preflight — run 10 minutes before, not during

```bash
venv/bin/python -m pytest tests/ -q
ls -la experiments/results/baseline_model.joblib
venv/bin/python -c "import os;print('GROQ key loaded:', bool(os.getenv('GROQ_API_KEY')) or 'check .env')"
```

Expect `65 passed`, and the joblib file present at ~590 MB.

**If Groq is down or out of quota**, everything except Step 2's explanation text
and Step 4 still works. Say so plainly and continue — that is itself the point
of the architecture, and Step 6 makes the argument without any network at all.

---

## Step 1 — The test suite (30 seconds)

> "Starting with the tests, so everything after this is trustworthy."

```bash
venv/bin/python -m pytest tests/ -q
```

**Expected:** `65 passed in ~3.5s`

**What to say:** 65 tests, up from 33. The new ones cover things that were
genuinely unprotected: `guardrails.py` had been in the pipeline since Week 3
with zero tests, while the *unused* ML guardrail had dedicated ones. There is
also now a test asserting the language model cannot set a verdict — the
invariant the whole redesign rests on.

---

## Step 2 — One alert through the pipeline (45 seconds)

> "Here is what the system actually does with a single alert."

```bash
venv/bin/python -m src.agent.run_agent --scenario evidenced
```

**Expected output:**

```
=== guardrails ===
  regex filter  : passed
  schema check  : passed

=== enrichment ===
  MITRE context : T1078 (Valid Accounts): Adversaries may obtain and abuse credentials...

=== verdict ===
  predicted     : BenignPositive
  triage path   : rf_primary
  RF margin     : 0.0986  (review threshold 0.2)
  confidence    : low

=== analyst explanation ===
  ...the confidence is low, so the verdict rests on a weak signal. Before acting,
  double-check the event logs for any signs of credential misuse...

=== disposition ===
  HELD FOR HUMAN REVIEW
```

**Point out three things:**

1. **MITRE enrichment resolved** from `T1078;T1078.004`. Until this week that
   returned nothing — the parser split on commas, but GUIDE uses semicolons.
   232 of 428 enrichable alerts had been silently losing their ATT&CK context.
   Resolution went from 45.8% to 100%.

2. **The margin is 0.0986, below the 0.20 threshold**, so it was held for a
   human rather than auto-actioned. The system knows when it does not know.

3. **The explanation says the verdict rests on a weak signal.** The model is
   describing the classifier's uncertainty honestly rather than manufacturing
   confidence. That is the behaviour the explanation prompt asks for, and it is
   what the LLM is genuinely good at.

---

## Step 3 — The same alert, old architecture (45 seconds)

> "Here is the same alert through last week's pipeline."

```bash
venv/bin/python -m src.agent.run_agent --scenario evidenced --legacy
```

**Expected:**

```
=== verdict ===
  predicted     : TruePositive
  triage path   : llm
  confidence    : high

=== disposition ===
  auto-accepted
```

**What to say — this is the strongest 20 seconds of the demo:**

Same alert. The old pipeline let the language model decide, it answered
**TruePositive** with **high confidence**, and it was **auto-accepted with no
human review**. The new pipeline held the same alert for review.

And "high confidence" from this model is precisely the signal that should not
be trusted: measured across 209 alerts, its high-confidence answers were
**25.6%** accurate while its medium-confidence answers were **38.3%**. Step 5
shows that measurement.

---

## Step 4 — The guardrails, honestly (45 seconds)

```bash
venv/bin/python -m src.agent.run_agent --scenario injection
```

**Expected:** `regex filter : blocked ['instruction_override:AlertTitle']`, no
verdict, held for review.

Then the same attack, rephrased:

```bash
venv/bin/python -m src.agent.run_agent --scenario injection_evasive
```

**Expected:** `regex filter : passed` — then
`schema check : blocked ['non_numeric_field:AlertTitle']`.

**What to say:** The regex filter caught the first phrasing and **missed** the
second. That is not a demo accident — measured against our own corpus, it
catches **1 of 20**. The schema check caught it anyway, because it does not try
to understand the attack: free text is not a valid `AlertTitle` whatever it
says. A type constraint cannot be evaded by rephrasing.

**Be first to state the limitation:** that works because GUIDE alert titles are
numeric codes. In a SOC where titles are prose, this check would not protect
that field.

---

## Step 5 — The control experiment (30 seconds) — **the centrepiece**

> "This is the experiment the whole decision rests on."

```bash
venv/bin/python experiments/rf_vs_llm_control.py
```

**Expected output:**

```
====================================================================
SAME 209 ALERTS, TWO MODELS
====================================================================
  RandomForest : accuracy 0.6555   macro F1 0.6035
  LLM          : accuracy 0.2823   macro F1 0.2121
  majority-class floor : 0.4928 (always answer BenignPositive)
  uniform-random floor : 0.3333

  McNemar: Of the 132 alerts where the two models disagreed in correctness,
  the RF was the correct one in 105. Under the null hypothesis that both
  models are equally accurate this split has p = 4.66e-12.

  Confidence gate: auto-accepts 160 alerts at 0.2562 accuracy,
                   escalates 49 at 0.3673 accuracy.
                   inverted: True

  RF training overlap: 4/209 rows (1.91%)
```

**Walk through it in this order:**

1. **The confound this removes.** Every earlier comparison scored the two models
   on *different* alerts — the router sent sparse alerts to the forest and
   well-evidenced ones to the language model. So a lower LLM score might just
   have meant harder alerts. This scores both on the **same 209 rows**.

2. **The alerts were not hard.** The forest gets 65.6% on them. Confound gone.

3. **The language model is below the floor.** 28.2% against the 49.3% you get by
   answering "BenignPositive" every time with no model at all. And these are the
   alerts the router picked as its *best case*.

4. **It is not luck.** On 132 alerts exactly one model was right; the forest was
   right on 105. McNemar's paired test gives **p = 4.66e-12**. Paired because
   both models saw identical inputs.

5. **It is not contamination.** Only 1.91% of these alerts appear in the
   forest's training data.

6. **The safety net was backwards.** The gate auto-accepted 160 alerts at 25.6%
   accuracy and escalated 49 at 36.7%. It was sending the *better* predictions
   to humans.

---

## Step 6 — What the fix achieved (20 seconds)

```bash
venv/bin/python -c "
import json
old = json.load(open('experiments/results/agent_metrics_week12_999_current.json'))
new = json.load(open('experiments/results/agent_metrics_week15_rf_primary.json'))
print(f\"  old hybrid      : accuracy {old['accuracy']}  macro F1 {old['macro_f1']}\")
print(f\"  RF decides      : accuracy {new['accuracy']}  macro F1 {new['macro_f1']}\")
print(f\"  same 999 alerts, same sample, same seed\")
"
```

**Expected:**

```
  old hybrid      : accuracy 0.6456  macro F1 0.6484
  RF decides      : accuracy 0.7347  macro F1 0.7307
  same 999 alerts, same sample, same seed
```

**What to say:** **+8.9 accuracy points, +8.2 macro F1**, on identical data,
with zero errors across all 999 alerts.

**If asked why it is below the 0.7718 baseline:** different tasks. The baseline
is on GUIDE's natural distribution where a constant answer scores 43.2%. This is
a balanced sample where a constant answer scores 33.3%. Over their floors:
**+40.1 versus +34.0**. The harder task, measured fairly, comes out ahead — and
this pipeline adds guardrails and a calibrated review gate the raw baseline
does not have.

*(To regenerate rather than read the file — takes about 7 minutes, so do not do
this live:)*

```bash
SOC_COPILOT_SKIP_EXPLANATION=1 venv/bin/python -m src.agent.evaluate \
  --sample-size 999 --output experiments/results/agent_metrics_week15_rf_primary.json
```

The skip flag is safe precisely because the explanation cannot affect a verdict.
Under the old design, skipping the LLM would have changed the result.

---

## Step 7 — Guardrail measurements (optional, 20 seconds)

```bash
venv/bin/python experiments/guardrail_layer_eval.py
```

Shows 5% regex recall broken down by attack family, 100% schema recall, and the
note that since this week injection cannot change a triage outcome at all.

---

## Step 8 — The clickable demo (optional, 60 seconds)

```bash
venv/bin/streamlit run src/app.py
```

Opens in a browser. Enter:

| Field | Value |
|---|---|
| AlertTitle | `15723` |
| DetectorId | `7` |
| Category | `Collection` |
| MitreTechniques | `T1078;T1078.004` |
| SuspicionLevel | `Suspicious` |
| LastVerdict | `Suspicious` |

Shows the verdict, the RF margin, the LLM explanation labelled as *not* deciding
the verdict, and the MITRE context. Stop with `Ctrl+C`.

**Note if asked:** the form used to collect "Title" and "Evidence", which no
part of the pipeline read — so whatever a user typed was silently discarded,
and those were also the only two fields the schema guardrail did not cover.
Fixed this week.

---

## Closing — say this before questions

> To answer the question directly: the language model is **not** worth its
> accuracy cost as a classifier. On identical alerts it scored 0.2823 against
> the Random Forest's 0.6555, below even a constant answer, with p = 4.66e-12.
> So I moved it off the decision path rather than defending it. The forest now
> decides every verdict and the model explains it — which improved the whole
> pipeline from 0.6456 to 0.7347 on the same 999 alerts and made prompt
> injection unable to change a triage outcome.
>
> The finding I would highlight is the confidence inversion: the model was
> *less* accurate when it claimed to be more confident, so the human-review
> safety net was auto-accepting its worst predictions. That is not visible
> unless you measure it, and nothing in the pipeline would have alerted us.
>
> The honest limitation is that the official test split is still unused —
> everything is evaluated on samples from the training file. That is the first
> thing I would fix.

---

## Things to raise with him — his decisions, not yours

1. **Paper declarations** (deferred on 11 August, now due): funding, competing
   interests, ethics approval, ORCID, repo visibility — and **co-authorship**,
   which is still a `TODO` in the author block.
2. **GeNIS integration and Wazuh Docker deployment** — pending sign-off since
   Week 10, unchanged.
3. **PR #25 is open and unreviewed**; this week's work is on `asma-week-15`.
4. **Three commits on `main`** (`7cbc58b`, `ad02c85`, `61ea961`) carry AI
   co-authorship trailers, which conflicts with the project's attribution
   policy. Rewriting shared history needs his decision.

---

## If something breaks mid-demo

| Symptom | Do this |
|---|---|
| Groq errors / quota exhausted | Say the explanation layer is down and the verdicts are unaffected — *that is the architecture working*. Steps 1, 5, 6, 7 need no network. |
| `FileNotFoundError: baseline_model.joblib` | Retrain: `venv/bin/python -m src.models.baseline` (~10 min). Do not start the demo without checking preflight. |
| Streamlit will not start | Skip Step 8. `run_agent.py` shows the same pipeline. |
| A number differs from this runbook | Say so out loud and open the JSON in `experiments/results/`. Every figure here is traceable to a committed file — reading from the source is a better look than glossing over it. |
