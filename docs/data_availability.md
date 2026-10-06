# Data Availability Statement — source of truth

Issue #44 (M6.1 PART B). This file is the single source for the
`Availability of data and materials` and `Code availability` entries in both
LaTeX drafts. Edit here first, then copy into
`docs/paper/latex/{ieee,springer}/*.tex`.

**Scope note.** This covers *data and code availability only*. Funding,
competing interests, ethics approval, consent, ORCID and authorship remain on
hold pending the author's sign-off (issue #16, 2026-08-11) and are deliberately
untouched here.

---

## Final text

> **Availability of data and materials.** The Microsoft GUIDE dataset
> (Freitas et al., 2024) is third-party data released under
> **CDLA-Permissive-2.0** and is not redistributed with this work. It is
> obtained from Kaggle (`microsoft/microsoft-security-incident-prediction`);
> `datasets/README.md` documents the download steps, and
> `datasets/INTEGRITY_MANIFEST.json` records the SHA-256 of the exact release
> every committed figure was computed from —
> `GUIDE_train.csv` (2.43 GB) and `GUIDE_Test.csv` (1.09 GB) — verifiable
> with `scripts/verify_data_integrity.py`. Re-running any classifier result
> therefore requires downloading GUIDE and retraining, because the fitted model
> `experiments/results/baseline_model.joblib` is 563 MB and is not
> redistributed; `src/models/baseline.py` regenerates it (~10 CPU-minutes).
>
> All evaluation outputs are committed as JSON/CSV under
> `experiments/results/`, and every table and figure in this paper is mapped
> one-to-one to its source artifact and regeneration command in
> `PAPER_FIGURE_MANIFEST.md`. Superseded results are retained under
> `experiments/results/archive/` with a README recording each file's numbers
> and what replaced it, so withdrawn figures remain inspectable rather than
> deleted. The leakage analysis specifically rests on
> `incident_leakage_audit.json`, `grouped_split_baseline.json` and
> `m2_1_splitmethod_delta_5seeds.json`. A per-cell statistical compliance
> audit is in `docs/statistical_compliance.md`.
>
> The **SOC-domain prompt-injection benchmark v1.0** introduced in this work —
> 400 attacks across seven families plus 100 real benign controls — is released
> with the code under the **MIT licence** and may be redistributed freely:
> `datasets/soc_injection_benchmark_v1.csv`, with its family-definition rubric
> at `datasets/soc_injection_benchmark_v1_RUBRIC.md` and a datasheet following
> Gebru et al. at `docs/soc-injection-benchmark-datasheet.md`. Note that its
> 100 benign control rows are derived from GUIDE and therefore inherit
> CDLA-Permissive-2.0; the 400 authored attack payloads are MIT.
>
> **Code availability.** All code is available at
> `https://github.com/AI-Security-Internships-2026/02-soc-copilot-threat-analysis`
> under the **MIT licence**, at commit `e7159c9fe4b185ccd571247d4e635f6666e85b47`. The clean-room reproducibility
> audit is logged in `docs/reproduce_from_scratch.log`.

---

## Deliberate omissions

- **Human-study ratings (M4.3 PART A).** Issue #44 asks for a de-identified
  ratings statement. Those ratings **do not exist yet** — M4.3 PART A needs real
  raters and is flagged on issue #40 for scheduling. No availability claim is
  made for data that has not been collected.
- **`m4_1_security_asr_runner.json`** arrives with PR #50 and is not yet on
  `dev`; the manifest lists it as pending rather than available.
