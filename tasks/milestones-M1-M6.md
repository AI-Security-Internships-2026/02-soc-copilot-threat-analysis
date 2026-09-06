# Milestones M1–M6 — issues #29–#47

**Issued:** 2026-09-06 by Hafiz Mati Ur Rahman (`Mati86`)
**Instruction:** *"I have created issues for you on your repo — please follow the issue # order and the timeline."*
**Supersedes:** the week-by-week workflow in `README.md`, and the Sep 8 submission date every document carried until this date.

Progress is recorded in `docs/weekly-progress.md` as before; this sheet is the map.

---

## Timeline

| Milestone | Due | Issues | Status |
|---|---|---|---|
| **M1 — Repo Stabilization** | **2026-09-08** | #29, #30 | **Done** — see below |
| M2 — Classifiers/Leakage | 2026-09-10 | #31, #32, #33, #34 | Not started |
| M3 — Guardrails/Benchmark | 2026-09-12 | #35, #36, #37 | Not started |
| M4 — Integrity/Explanation | 2026-09-15 | #38, #39, #40, #41 | Not started |
| M5 — Ablations/Cost | 2026-09-17 | #42, #43 | Not started |
| **M6 — Manuscript/Submission** | **2026-09-20** | #44, #45, #46, #47 | Not started |

Target venue is **Elsevier *Computers & Security*** (22 pages, 12 sections), with **IEEE IoT
Journal** as the alternate — issue #47.

---

## M1 — Repo Stabilization (due Sep 8) — complete

### M1.1 (#29) — clean-room reproducibility audit

- [x] Fresh virtualenv created from scratch
- [x] `pip install -r requirements.txt` — **zero manual fixes needed**
- [x] `docs/venv_freeze_audit.txt` committed
- [x] Baseline-1 test suite → captured
- [x] Baseline-2 paired RF-vs-LLM control → 0.6555 / 0.2823 / p = 4.66e-12
- [x] Baseline-3 held-out `GUIDE_Test.csv` → 0.6998 / 0.6949 / AUC 0.8775
- [x] Baseline-4 incident-level leakage diagnostic → −0.0283, 95% CI [+0.0199, +0.0368]
- [x] `docs/reproduce_from_scratch.log` committed

**Two deviations, stated in the log rather than glossed:**

1. The issue specifies **WSL2**; this machine is macOS. The substantive equivalent was run — new
   venv, unmodified `requirements.txt`, full captured output — but *the claim that the pins resolve
   on WSL2 specifically is not evidenced by this log and remains open.*
2. The issue names `experiments/evaluate_baseline.py` and `models/baseline_model.joblib`. Neither
   exists. The real equivalents (`experiments/guide_test_holdout_eval.py`,
   `experiments/results/baseline_model.joblib`) were used.

The issue also expects 102 passing tests; the suite is larger. That is added coverage, not drift.

### M1.2 (#30) — repo audits and security wiring

**Part A — stale numeric claims** → `docs/stale_claims_audit.md`
- [x] 94 hits across 22 files, each with file, line, value, action and rationale
- [x] `3.616 µs` corrected to the measured 1.93 µs / 5.56 µs
- [x] `"p_value": 0.0` — **zero occurrences**; already reported as `4.66e-12` everywhere
- [x] Seven uncaveated prose sites annotated or corrected; result artifacts and code comments
      deliberately left untouched, with the reasoning recorded

**Part B — HITL gate calibration** → `config/config.py`, `tests/test_hitl_gate_invariants.py`
- [x] Deployed path confirmed margin-only; no routing conditional reads a confidence string
- [x] `T_init` / `HITL_AUTO_ACCEPT_MARGIN` declared with the sweep it was chosen from
- [x] 20 tests, including the causal one: swapping the LLM's confidence never changes routing
- [x] **0.20 vs 0.12 reconciled — keep 0.20.** M5.1 has not run; the committed sweep has no 0.12
      point and its neighbours are worse; 0.20 already gives the 80/20 split 0.12 was aimed at

**Part C — DetectorId and feature inclusion** → `experiments/field_inclusion_audit.py`, `docs/field-inclusion-memo.md`
- [x] 500,000-row audit: `DetectorId` 0/4,559 non-numeric, `AlertTitle` 0/33,042 non-numeric
- [x] Assertion added to `tests/test_schema_guardrail.py`
- [x] `LastVerdict`/`SuspicionLevel` confirmed present in the feature matrix, ablated, and
      **measured at 0.0022 accuracy** on the held-out split — decision: keep, document as
      analyst-derived

**Part D — data integrity** → `datasets/INTEGRITY_MANIFEST.json`, `scripts/verify_data_integrity.py`
- [x] SHA-256 manifest for both CSVs with size and mtime
- [x] Verifier written and run → exit 0
- [x] `datasets/README.md` sections (A) citation, (B) Kaggle CLI, (C) alternative, (D) integrity check

---

## Reading the issues

Two habits worth keeping for M2–M6, both learned in M1:

- **The issues cite paths and counts from an earlier snapshot.** Check every path against the repo
  before running a command from an issue verbatim.
- **Where an instruction cannot be followed literally, do the substantive equivalent and say so in
  the committed artifact.** Reporting a WSL2 audit that was not run on WSL2 would be exactly the
  kind of unverified claim M1 exists to eliminate.
