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
| M2 — Classifiers/Leakage | 2026-09-10 | #31, #32, #33, #34 | **Done, one sub-issue partial** — see below |
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

## M2 — Classifiers/Leakage (due Sep 10) — done, #32 partial

### M2.1 (#31) — leakage methodology validation suite

**PART A — 5-seed split-method delta** → `experiments/m2_1_splitmethod_5seeds.py`,
`experiments/results/m2_1_splitmethod_delta_5seeds.json`
- [x] 5 GroupShuffle seeds on the shared 100,000-row slice, RF-200/LabelEncoder config
- [x] Mean Δ_acc = +0.0306 (std 0.0075), 95% CI [+0.0232, +0.0361], overlaps the paper's
      single-seed [+0.0199, +0.0368]
- [x] Wilcoxon p=0.0625 — the *exact floor* achievable with 5 same-signed paired seeds, not a
      failure to detect an effect (the CI already excludes 0)

**PART B — 300K leakage audit, 3-seed replication** → `experiments/incident_leakage_audit.py --seeds`,
`experiments/results/m2_1_leakage_300k_balanced.json`
- [x] `incident_leakage_audit.py` reproduces §4.12 exactly (leaked 0.8332, clean 0.5898,
      +0.2433 [+0.2282, +0.2587])
- [x] 3-seed replication: mean Δ = +0.2416 (std 0.0022) — within ±0.01 of +0.2433, std < 0.005
- [x] `Δ_TP > Δ_FP > Δ_BP` ordering confirmed across seeds

**PART C — 4-point overlap scatter** → `experiments/overlap_audit.py`,
`experiments/m2_1_historical_eval_overlap.py`, `experiments/results/m2_1_overlap_scatter.csv`
- [x] `overlap_audit.py` reproduces all three Table 14 pairs exactly (999-set 1.40/55.76,
      209-set 1.91/39.23, GUIDE_Test n=999 0%/0%)
- [x] 4th point (GUIDE_Test n=15,000, 0% overlap by construction) added
- [x] Pearson r=0.11 (p=0.89) — **does not meet the issue's expected r≥0.90**, reported as
      measured. The 209-alert point is confounded: its subset (evidence_field_count≥2) is
      intrinsically harder for the RF than a typical alert (Week 12), independent of contamination

### M2.2 (#32) — third-party Kaggle reproduction — **blocked, not attempted-and-faked**

- [ ] Blocked on tooling access: Kaggle's notebook listing/code viewer are client-side rendered
      (`WebFetch` returns only the page title); no `kaggle` API key is configured; live-browser
      access would require asking the user to pick between two connected Chrome sessions for a
      P2-optional sub-task, which this pass chose not to do unprompted
- [x] Real candidate notebooks identified via web search and cited, with attribution, in
      `experiments/kaggle_repro/README.md` for whoever completes this with API/browser access

### M2.3 (#33) — evaluation protocol + grouped model deploy

**PART A — EVAL_PROTOCOL.md** → `EVAL_PROTOCOL.md` (repo root)
- [x] 4 sections: background, three protocols (A=PREFERRED/B=ACCEPTABLE/C=LAB_INFLATED),
      reproduction steps per mode, 4-item compliance checklist
- [x] Every M2 output script tags its own `"protocol"` field at the point it writes a result
      (4 scripts do this, not just the required 2)

**PART B — grouped-trained model deploy** → `experiments/m2_3_deploy_grouped_model.py`,
`experiments/results/m2_3_grouped_deployed.json`, `docs/m2-3-deploy-decision-memo.md`
- [x] `GroupShuffleSplit` on `(OrgId, IncidentId)`, 500,000 rows (M2.4's heldout training budget),
      **0 incidents verified crossing the split boundary**
- [x] Re-scored on the paper's existing samples: GUIDE_Test 15K (+0.0296 vs deployed 0.6998),
      A4-pipeline 999 (+0.0631 vs deployed 0.7347)
- [x] `models/best_grouped_classifier.joblib` saved (candidate only — `baseline_model.joblib`
      untouched); deploy-compatible without a wrapper
- [x] Decision memo: **KEEP for M2–M5, adopt at M6** — a deliberate single swap once M3–M5's own
      numbers exist, not a mid-schedule change. Full reasoning in the memo.
- [ ] Control-node arms (a)/(b) invariant re-check against the candidate artifact — not re-run
      (the invariant is architectural, not model-dependent, and already proven in
      `control_node_ablation.json`); noted rather than silently skipped

### M2.4 (#34) — 7-classifier baseline suite — P0-critical, done

→ `experiments/m2_4_classifier_suite.py`, `experiments/results/m2_4_validate_5seed.json`,
`experiments/results/m2_4_heldout_n15k.json`, `experiments/results/m2_4_best_model_selection.json`,
`experiments/results/m2_4_m7_llm_only.json`

- [x] Dispatcher runs all 7 models (`--model_id`) in both modes (`--mode validate|heldout`)
- [x] Heldout (GUIDE_Test n=15,000): M1 0.3333, M2 0.5443, **M3a 0.7294 (winner)**, M3b 0.7267,
      M4 0.7201, M5 0.7052, M6 0.7057
- [x] McNemar M6-vs-M3a (p=2.19e-14) and M3a-vs-M3b (p=0.0372) reported
- [x] McNemar M3a-vs-M7 (the selected model against the LLM, on the same 241 scored rows):
      p=8.75e-10, RF correct on 111/148 discordant alerts. `experiments/results/m2_4_m3a_vs_m7_mcnemar.json`
- [ ] McNemar M6-vs-M7 specifically — **not computed**; would need a second ~57-minute
      default-hyperparameter CatBoost fit under this machine's memory ceiling after the week's
      other CatBoost runs, for a pairing against the runner-up rather than the selected model
- [x] Cochran's Q across tabular M1–M6: p≈0
- [x] `models/best_classifier.joblib` selection: **M3a retained** — no alternative cleared both
      the >1.5-point gap and McNemar p<0.05 bar against it
- [x] M3a-vs-M3b interpretation: LabelEncoder's ordinal numbering **measurably helps** (+0.27pts,
      p=0.037) — answers independent review §31 directly, in the opposite direction the review
      worried about
- [x] M7 (LLM-only): **241/500 scored** (Groq's ~200,000-token/day quota exhausted mid-run) —
      accuracy 0.3291, **below the 0.3333 majority-class floor**, confirming the issue's
      expectation at the n quota allowed. Resumable via checkpoint for the remaining 259.

---

## Reading the issues

Two habits worth keeping for M2–M6, both learned in M1:

- **The issues cite paths and counts from an earlier snapshot.** Check every path against the repo
  before running a command from an issue verbatim.
- **Where an instruction cannot be followed literally, do the substantive equivalent and say so in
  the committed artifact.** Reporting a WSL2 audit that was not run on WSL2 would be exactly the
  kind of unverified claim M1 exists to eliminate.
