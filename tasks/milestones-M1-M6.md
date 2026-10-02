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
| M2 — Classifiers/Leakage | 2026-09-10 | #31, #32, #33, #34 | **Done, one sub-issue blocked** (#32 tooling) — see below |
| M3 — Guardrails/Benchmark | 2026-09-12 | #35, #36, #37 | **Done**, two #36 criteria open (L2/L3 latency; one mis-specified) |
| M4 — Integrity/Explanation | 2026-09-15 | #38, #39, #40, #41 | **Partial** — #38/#41 done but unmerged (PR #50); #39 not started; #40 PART A needs raters |
| M5 — Ablations/Cost | 2026-09-17 | #42, #43 | **Done** — see below |
| **M6 — Manuscript/Submission** | **2026-09-20** | #44, #45, #46, #47 | **Done**, one gap (#45 PowerShell dry-run unrunnable here) |

**Status last verified against artifacts on 2026-09-29**, not against issue state. Six of these
issues carry `MERGED:` in their titles as written on 2026-09-06; that string is part of the
original title text and is **not** a completion marker. Issues are closed by Mati or Rana, never
by the author, so an open issue is not evidence of outstanding work and a closed one would not be
evidence of finished work. Every status above was checked by reading the committed artifact.

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
- [x] McNemar+odds ratio, all 3 required pairs, on the completed n=500 M7 arm (superseding the
      earlier 241-row partial figures below): M6-vs-M3a p=2.19e-14 (OR 0.72), M3a-vs-M3b p=0.0372
      (OR 1.25), M6-vs-M7 p=3.17e-17 (OR 2.84), M3a-vs-M7 p=2.22e-18 (OR 2.94) — RF wins the
      large majority of discordant pairs against the LLM in both tabular comparisons.
      `experiments/results/m2_4_heldout_n15k.json`'s `mcnemar_pairs` field.
      `experiments/results/m2_4_m3a_vs_m7_mcnemar.json` is the superseded n=241 partial figure,
      kept for history.
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

## M3 — Guardrails/Benchmark (due Sep 12) — done, two #36 criteria open

### M3.1 (#35) — SOC-domain injection benchmark v1.0 — P0-critical, done

→ `datasets/soc_injection_benchmark_v1.csv`, `experiments/m3_1_generate_benchmark.py`,
`experiments/m3_1_interrater_kappa.py`, `docs/m3-1-kappa-results.md`

- [x] 500 rows: 400 attacks across 7 families + 100 real GUIDE `BenignPositive` controls
- [x] Family counts exactly as specified (F1=60, F2=55, F3=60, F4=55, F5=50, F6=60, F7=60)
- [x] Controls are real, not synthetic: reservoir-sampled unique-incident rows scored with the
      deployed classifier, top of the entropy ranking — the hard-looking benign cases
- [x] Rubric (`datasets/soc_injection_benchmark_v1_RUBRIC.md`) with family definitions and five
      edge-case rules, fixed **before** any detector ran
- [x] **Inter-rater Cohen's κ = 0.8178** on a blinded 100-row subset, above the κ ≥ 0.75 bar.
      Raw agreement 91/100. Both returned sheets committed verbatim; the pass was not re-run.
- [x] 100-subset disagreement resolution log, all 9 rows, in `docs/m3-1-kappa-results.md`

**The κ is reported with its ceiling, not without.** All 50 controls in the subset are bare
numeric GUIDE codes and all 50 attacks are prose, so the classes separate on surface form alone.
The raters agreed on 50/50 controls and **every one of the 9 disagreements is an attack row**
(attack-only agreement 41/50). The pooled figure therefore establishes that the labels are
unambiguous to independent readers and nothing stronger — it is not evidence the corpus is hard.
That ceiling was written into the datasheet and rubric *before* the raters were sent anything,
and the returned ratings confirm it rather than dispelling it.

Adjudication in the resolution log is against the benchmark's **construction key**, not a third
human rater. Stated explicitly so the rater-accuracy figures (0.97 / 0.90) are not misread as a
second κ.

### M3.2 (#36) — 7-detector benchmark — done, two criteria open

→ `experiments/m3_2_heuristic_detectors.py`, `experiments/m3_2_learned_detectors.py`,
`experiments/m3_2_build_detector_matrix.py`, `docs/m3-2-detector-family-matrix.md`

- [x] Heuristic dispatcher: H1 regex 2.75%, H2 schema 10.50%, H3 SOC-aware 91.25%,
      H-union 96.75% — all at **0% FPR** on the 100 real controls
- [x] Learned dispatcher: L1 TF-IDF 3.25%, L2 Prompt Guard 2 31.25%, L3 LLM self-check 58.99%
- [x] L1 negative-transfer check: legacy 40-row ROC-AUC 0.46 (within the ±0.05 bar), falling to
      **0.1978** on the 500-row benchmark — negative transfer confirmed at scale, not a
      small-sample artifact
- [x] 7 × 7 failure matrix with a real `benchmark_id` cited in every cell's mechanism sentence
- [x] Figure-ready CSVs, emitted from the same in-memory matrix the markdown renders from
- [ ] **L2/L3 latency not captured.** Only L1 has `latency_ms_per_1000_rows` and p50/p99. The two
      detectors where latency actually matters are live quota-metered Groq calls; measuring them
      needs API budget that has not been spent on it.
- [ ] **One criterion is mis-specified and is not being quietly re-pointed.** It asks for
      "H2 = 100% TPR on M3.1 F1/F2 numeric attacks". Measured: **F1 0.15, F2 0.1636.** The only
      1.0 in the artifact is `h2.tpr_on_alerttitle_subset` over a *narrower* denominator (n=42).
      Re-scoping or retiring this belongs to whoever set it; aiming the test at the denominator
      that passes would make the criterion meaningless.

**Two deliberate scope changes, both on instruction, both recorded:**

1. The OpenAI Moderation detector was **removed from scope by the supervisor** (issue #36), and
   the old L4 renumbered to L3. That is a relabel, not an extra run — `docs/m3-2-l3-decision-memo.md`.
   The matrix is therefore 7 detectors × 7 families = 49 cells, not the 56 the issue anticipated
   from 8 detectors.
2. L3 is `complete: false` at **495/500 scored** — five F4 payloads return a reproducibly
   unparseable response. Its recall is reported over the 395 attacks it actually scored rather
   than crediting it with five rows it never resolved.

**The issue's expected narrative was not confirmed, and is reported as measured.** #36 anticipated
that F3/F4/F6 would evade everything, motivating M4 as "input-only defence is insufficient".
H-union leaves **zero families below 50%** (weakest is F4 at 76.36%) and `uncovered_families` is
empty. `docs/m3-2-detector-family-matrix.md` states this plainly rather than adjusting to the
expectation. The architectural finding is unaffected and does not depend on it: since Week 15 the
LLM assigns no verdict, so even a genuinely uncovered family degrades an explanation, not an
outcome. Note also that **H-union is not what ships** — the deployed filter is H1 ∪ H2, at ~13%
recall on this benchmark, and the paper says so where it uses the H-union number.

### M3.3 (#37) — datasheet, one-click repro, regression tests — done

→ `docs/soc-injection-benchmark-datasheet.md`, `scripts/benchmark_soc_injection.py`,
`tests/test_guardrail_benchmark_regression.py`

- [x] Datasheet following Gebru et al., all 8 sections, with **five** known biases stated plainly
- [x] κ quoted explicitly, with the attack-only stratum and its chance-agreement caveat
- [x] MIT licence statement; abstract present (169 words — the heading no longer overstates it)
- [x] One-click dispatcher with `--detector {l1,l2,l3,h1,h2,h3,h_union,all}`, live calls behind
      `--daily-call-budget`, checkpoint/resume
- [x] **SHA-256 certificate committed** at `experiments/results/m3_benchmark_checksums.json`;
      `--reproduce_only_checksum` verifies against it and exits non-zero on drift. Hashes are over
      content with `generated_at_utc`/`git_sha` stripped, because one target carries a timestamp
      and a byte-level hash drifted on every no-op re-run — the exact false alarm the check exists
      to prevent.
- [x] 5 new regression assertions, 5/5 passing. One caveat: `test_h2_numeric_field_tpr_is_100_percent`
      asserts the AlertTitle-subset figure, not the numeric-field figure its name implies — the
      same mis-specification as #36 above, flagged rather than renamed to hide it.

---

## M4 — Integrity/Explanation (due Sep 15) — partial

### M4.1 (#38) — 8-config security ASR runner — done, **not on this branch**

→ `experiments/m4_1_security_asr_runner.py`, `experiments/results/m4_1_asr_8configs.json`
(on `asma-week-20-m4-integrity`, PR #50 — draft, 24 commits behind `dev` and conflicting)

- [x] 8-config runner with per-family stats, CIs and McNemar
- [x] A4's label-path Triage-ASR is **0.0000 by construction, not by measurement** — the LLM
      assigns no verdict, so there is no channel through which an injection could move one. The
      paper states it as a structural property; reporting it as a won contest would be the wrong
      claim, and `tests/test_paper_claims.py` (as repaired on PR #56) asserts the structural form.
- [x] The A4 **explanation channel** is the only genuinely attackable surface, and it is scored
      against the pre-injection alert — PR #55.
- [ ] Blocked from `dev` by PR #50's merge state, not by missing work.

### M4.2 (#39) — corrected-sequencing ablation re-run — **not started, deliberately**

- [ ] Every substantive criterion is unmet: `control_node_ablation.json` is still the 2026-09-06
      run, arm (d) at **33 scored / 966 unscored**, arm (c) bin-2 at n=6 and bin-3 at n=0
- [ ] No `control_node_ablation_resolved_sequencing.json` exists

**Why it is not started rather than partially done.** Hitting the coverage targets needs ~2,000
Groq calls paced across 2–3 days of a hard ~200,000-token/day quota. A partial run reproduces
exactly the under-coverage the issue exists to fix, and would replace an honest caveat with a
second under-powered number. The issue is P2-optional and the limitation is already carried in the
paper verbatim, so the current state is the more defensible one until quota is allocated.

### M4.3 (#40) — explanation-quality human study — PART A blocked

- [ ] **PART A needs real human raters and cannot be simulated.** No de-identified ratings dataset
      exists, and `docs/data_availability.md` makes no availability claim for one —
      `tests/test_manifest_integrity.py` asserts that honesty.
- [x] The M3.1 κ pass has now demonstrated the two-rater apparatus end to end (blinded sheets,
      distributable packet, scoring script, resolution log), so the workflow is not the blocker;
      recruitment is.
- [x] Automated proxies exist meanwhile via M5.1's explanation study (D1 groundedness, D2 MITRE
      match) — reported as proxies, not as analyst judgement.

### M4.4 (#41) — best-classifier re-wiring — done, **not on this branch**

→ `src/models/classifier_factory.py`, `tests/test_best_classifier_integration.py`
(on `asma-week-20-m4-integrity`)

- [x] Factory committed; A4 graph reads the selected classifier rather than a hardcoded RF
- [x] 3 integration tests
- [ ] Blocked by the same PR #50 merge topology as #38. **This is a merge problem, not an
      engineering one** — rebasing PR #50 onto `dev` unblocks #41 and PR #55 together.

---

## M5 — Ablations/Cost (due Sep 17) — done

### M5.1 (#42) — ablations and review-gate burden

→ `experiments/results/m5_1_ablation_5config.json`, `m5_1_burden_sweep.json`

- [x] Three ablation arms (`nomitre`, `noguardrails`, `nohitl`) against `full`, on the held-out
      15,000: **0 label differences out of 15,000 in every arm**, by exact element-wise identity
- [x] Burden sweep on the same held-out set (n=15,000, 0% incident overlap), not a train-sampled
      one — an operating point tuned on leaked data would not survive deployment

**The strongest form of the architectural claim, and it is a proof rather than a tolerance.** No
non-deciding stage can move a verdict: not MITRE enrichment, not the guardrails, not the review
gate. That is 0 differences across 15,000 rows, not "no significant difference".

**The prediction that did not hold, kept as stated.** #42 predicted D1 groundedness would fall
≥ 10 points without MITRE context. Measured: **0.97 → 0.89, a drop of 8.0 points** (Fisher
p = 0.0489 — significant, but under the prediction). D2 fell 12.7 points but is **not**
significant at n=55. The mechanism explains the ceiling: `build_context` injects the raw technique
ID regardless of enrichment, so enrichment only adds the ATT&CK description. Reported as measured.

### M5.2 (#43) — cross-domain transfer and per-stage cost

→ `experiments/results/m5_3_wazuh_t1.json`, `m5_4_latency_cost.json`

- [x] Wazuh Tier-1 synthetic 10,000: verdict agreement **0.9637** [0.9598, 0.9673], exact
      Clopper-Pearson. Recorded as **schema-transfer fidelity, not accuracy** — the field is named
      `accuracy_comparison_not_reported` precisely so the number cannot be misquoted as accuracy.
- [x] Per-stage latency and cost: fast path 17.7 ms (56.5 alerts/s), routed path 1.78 s
      (0.562 alerts/s). **The LLM is 99.0% of routed-path latency**; the router cuts API spend
      4.78×.

**A defect found by measurement, and deliberately not fixed.** The Wazuh adapter's
`_suspicion_level()` emits `low/medium/high`, but the deployed encoder holds only
`['Incriminated','Suspicious','nan']` — all three encode to −1, so every Wazuh alert silently
loses `SuspicionLevel`. Left unfixed because changing it changes deployed behaviour mid-schedule;
recorded so it is not rediscovered as a surprise.

---

## M6 — Manuscript/Submission (due Sep 20) — done, one gap

### M6.1 (#44) — figure manifest, data availability, compliance audit

- [x] `PAPER_FIGURE_MANIFEST.md`, **generated** rather than hand-written, cross-checking 0 missing
      and 0 unclaimed on every run — `tests/test_manifest_integrity.py` fails the suite otherwise
- [x] `docs/statistical_compliance.md` at 100%, with five stated exemptions
- [x] `m6_1_effect_sizes.json` — McNemar odds ratios with **Holm–Bonferroni** family-wise
      correction at α = 0.05
- [x] `docs/data_availability.md` — data and code availability written
- [ ] Funding, competing interests, ethics, consent, ORCID and authorship **deliberately left
      blank**, per Dr. Rana on issue #16. They need the author's sign-off, not a default. The
      availability text's source of truth is `docs/data_availability.md`; the held-back five trace
      to Dr. Rana's instruction on issue #16. Do not fill these in unprompted.

### M6.2 (#45) — one-click reproduction runner

- [x] `scripts/reproduce_all.{sh,ps1}`, 29 steps, verified identical in sequence over 27 script
      paths and 32 step labels
- [x] Bash dry-run log committed; the M3.1 κ step is now live rather than skipped
- [ ] **PowerShell dry-run never produced.** No `pwsh` on this machine (Homebrew blocked by an
      untrusted tap). Structural equivalence is verified, but **a genuine PowerShell syntax error
      remains possible** — stated in `docs/repro_logs/README.md` rather than implied to be fine.

### M6.3 (#46) — paper-claims regression suite

- [x] `tests/test_paper_claims.py`, 31-cell CI backfill in `m6_3_ci_backfill.json`
- [x] Claims whose experiment has not run are **skipped with the issue number that will produce
      them** — never asserted against a placeholder, never dropped so the count looks better
- [x] The three ASR claims named the wrong artifact (`m4_1_security_asr_runner.json`, the runner
      *script's* name, versus the `m4_1_asr_8configs.json` PR #50 actually ships), so they would
      have kept skipping silently after that PR merged. Repaired on PR #56, along with the claims
      themselves — A1's ASR is "nonzero but small", not ≥ 0.25, and the A1-vs-A4 McNemar is
      degenerate by construction.
- [ ] `not_backfillable` entries are listed with the reason and the substitute source, rather
      than left as silent blanks.

### M6.4 (#47) — journal manuscript

- [x] 12 sections, none placeholder-only, `elsarticle.cls`, 3 title candidates
- [x] Abstract **241 words**, inside the stated 150–250 band
- [x] 25 tables (≥ 5 required), 7 figures (≥ 6 required)
- [x] **50 references**, each verified against a DOI record, programme page or publisher listing
      before being written in — see `docs/literature-review.md` references 14–37. Every bibitem is
      cited; no citation dangles; none in the abstract.
- [x] Limitations section with 15 bullets, including the ones that cost something to state
- [x] Three contribution sentences (leakage, guardrail transfer, architecture)
- [x] Compiles clean via `tectonic` (which fetches `elsarticle`; local TeX Live lacks it)

**On the "22 pages" in the issue title.** It appears in the title only — not in any acceptance
criterion, concrete task or bullet — and *Computers & Security* sets no hard page limit. The draft
is 29 pages. That is recorded as a fact, not treated as a failed criterion, and the manuscript was
not cut to reach a number nobody wrote down.

**Where the manuscript lives.** Not in this repository, by Dr. Rana's instruction during PR #24
review. It is on the local branch `overleaf-onto-remote` and syncs to the private Overleaf remote
only — never to `origin`. That is policy, not an oversight or a backup gap.

---

## Outside the milestone set

**#51 — demo video (Rana, due Sep 18).** Not done. `docs/demo-runbook.md` holds a complete,
live-verified beat-by-beat script, including the before/after leakage moment the issue asks to
lead with (0.7347 → 0.6998, seven seeds, Wilcoxon p = 0.0156). Only the recording is missing —
roughly fifteen minutes. Two fixes first: the script plans 3–5 minutes against a 2–3 minute ask
(cutting beats 4–5 lands it in range), and its preflight line still says "expect 171 passed" when
the suite is 243.

---

## Reading the issues

Two habits worth keeping for M2–M6, both learned in M1:

- **The issues cite paths and counts from an earlier snapshot.** Check every path against the repo
  before running a command from an issue verbatim.
- **Where an instruction cannot be followed literally, do the substantive equivalent and say so in
  the committed artifact.** Reporting a WSL2 audit that was not run on WSL2 would be exactly the
  kind of unverified claim M1 exists to eliminate.
