# M2.2 (issue #32) — third-party leakage reproducibility

**Status: attempted and completed, with two honest deviations from the
issue's literal spec.** `~/.kaggle/kaggle.json` credentials were available
this session (not checked, or not present, previously) — the real Kaggle
API (`kaggle kernels list --dataset
Microsoft/microsoft-security-incident-prediction --sort-by voteCount`)
gives ranked, real vote counts, superseding the websearch-only attempt
recorded below. Results: `experiments/results/m2_2_kaggle_baselines.json`
(combined), `m2_2_kaggle_notebook_1.json` / `m2_2_kaggle_notebook_2.json`
(per-notebook). Scripts: `kaggle_notebook_1.py` (CatBoost, ported from
kugakugar/catboost, 39 votes), `kaggle_notebook_2.py` (RandomForest, ported
from mohamedamr992/94-roc-randomforest, 16 votes).

**Deviation 1 — no notebook on this dataset reaches the issue's "≥50
upvotes" bar.** The real ceiling is 39 votes (kugakugar/catboost). Used the
top-voted notebook anyway rather than treating this as another blocker.

**Deviation 2 — the literal 2nd-highest-voted notebook doesn't fit the
task.** safreita/incident-triage-prediction (26 votes) trains directly on
GUIDE_Train.csv and scores on GUIDE_Test.csv with no `train_test_split`
call anywhere in it — there is no row-level split in it to patch to
GroupShuffleSplit. The next candidate down,
alexandrepedrosai/majorana-hardware (21 votes), is unrelated to this
dataset entirely despite the vote-count/tag association. Used
mohamedamr992/94-roc-randomforest (16 votes), the next-highest-voted
notebook that actually performs a row-level split — see
`kaggle_notebook_2.py`'s module docstring for the full chain of rejections.

**Result: the issue's AC ("at least one notebook shows delta_acc ≥
+0.020") is not met** — 0.0070 and 0.0092 respectively, both real,
positive, same-direction results, both smaller than this project's own
+0.0283 finding. See `m2_2_kaggle_baselines.json`'s `interpretation` field
for why (binary vs. this project's 3-class target formulation). Reported
as a real negative result, not adjusted or hidden.

---

## Original blocked-attempt record (superseded above, kept for context)

*The following was true of the first attempt this session, before Kaggle
API credentials were found at `~/.kaggle/kaggle.json`:*

## What the issue asks for

Port the top-2 most-upvoted public Kaggle notebooks that classify the GUIDE
dataset, run each in (a) its original row-level `train_test_split` and (b) a
patched `GroupShuffleSplit`-by-`IncidentId` version, and report the delta —
evidence that M2.1's leakage finding is a dataset-wide evaluation artifact,
not specific to this project's own code.

## Why it wasn't done this session

Two things this task needs were not available without a step this session
chose not to take unilaterally:

1. **Vote counts and notebook code require rendering Kaggle's page in a real
   browser.** `WebFetch` returns only the page `<title>` for both the
   dataset's Code tab (`kaggle.com/datasets/Microsoft/microsoft-security-incident-prediction/code`)
   and individual notebook pages — Kaggle's notebook listing and the code
   viewer are both client-side rendered, and nothing in the returned HTML
   carries vote counts or source cells. A live headless-Chrome session
   could read the rendered page, but this account has two connected Chrome
   browsers with neither pre-selected, and picking one requires asking the
   user directly (`AskUserQuestion`, per the browser tool's own
   requirement) — not something to do unprompted for a P2-optional task
   mid-background-session.
2. **No `kaggle` API credentials are configured.** `requirements.txt`'s own
   Week 17 changelog records that the `kaggle` package was removed because
   nothing in the codebase imports it; `.env` carries only `GROQ_API_KEY`.
   The Kaggle API (`kaggle kernels list --dataset ...`) would return real,
   sortable vote counts without a browser, but needs a key this environment
   doesn't have.

## What a real websearch did surface

Not vote-count-verified, but real, named, linked notebooks that classify
this exact dataset — a starting point for whoever picks this up with
Kaggle API access or a selected browser session:

- ["Microsoft Security Incident EDA+Modelling"](https://www.kaggle.com/code/adveatprasadkarnik/microsoft-security-incident-eda-modelling) — adveatprasadkarnik
- ["Incident Triage Prediction"](https://www.kaggle.com/code/safreita/incident-triage-prediction) — safreita (the same account that mirrors this dataset at `kaggle.com/datasets/safreita/microsoft-security-incident-prediction`)
- ["Microsoft Security Incident Prediction"](https://www.kaggle.com/code/sanjanasharma1/microsoft-security-incident-prediction) — sanjanasharma1

## To complete this

1. Either configure a `kaggle` API key (`~/.kaggle/kaggle.json`) and run
   `kaggle kernels list --dataset microsoft/microsoft-security-incident-prediction --sort-by voteCount`
   to get real, ranked vote counts, or ask the user which connected Chrome
   browser to use and read the rendered Code tab directly.
2. Pick the top 2 by vote count that do a `train_test_split`-based
   classification (not pure EDA).
3. Port each into `kaggle_notebook_1.py` / `kaggle_notebook_2.py` in this
   directory, `random_state=42`, with an attribution comment linking the
   original.
4. Run unmodified, capture `original_split_acc`/`original_macro_f1`; patch
   the split to `GroupShuffleSplit(n_splits=1, test_size=0.2,
   groups=IncidentId, random_state=42)`, rerun, capture
   `groupsplit_acc`/`groupsplit_f1`.
5. Write `experiments/results/m2_2_kaggle_baselines.json` per the issue's
   acceptance criteria.
