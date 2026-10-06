<#
.SYNOPSIS
  One-command reproduction of every experiment behind the paper (issue #45, M6.2).

.DESCRIPTION
  PowerShell mirror of scripts/reproduce_all.sh. Identical command sequence and
  identical step numbering, so a reviewer on Windows without WSL2 gets the same
  run. Typical runtime ~6-12 hours on a CPU laptop with default flags.

  Fails fast: the first non-zero exit stops the run, because a later stage
  reading a half-written result is worse than stopping.

.EXAMPLE
  .\scripts\reproduce_all.ps1
  .\scripts\reproduce_all.ps1 -DryRun
  .\scripts\reproduce_all.ps1 -IncludeApi -IncludeKaggle
  .\scripts\reproduce_all.ps1 -SkipHeavy
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$IncludeApi,
    [switch]$IncludeKaggle,
    [switch]$SkipHeavy,
    [switch]$Gpu
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

# On Windows the venv layout is Scripts\python.exe, not bin/python.
$PY = if (Test-Path 'venv\Scripts\python.exe') { 'venv\Scripts\python.exe' } else { 'venv/bin/python' }
$OUT = 'experiments/paper_ready'
$script:Step = 0
$TOTAL = 29

if ($Gpu) { $env:SOC_COPILOT_USE_GPU = '1' }

function Say([string]$Msg) {
    Write-Host ""
    Write-Host ("[{0,2}/{1}] {2}" -f $script:Step, $TOTAL, $Msg) -ForegroundColor White
}

function Invoke-Step {
    param([string]$Name, [string[]]$Cmd)
    $script:Step++
    Say $Name
    if ($DryRun) {
        Write-Host ("        would run: {0} {1}" -f $PY, ($Cmd -join ' '))
        return
    }
    & $PY @Cmd
    if ($LASTEXITCODE -ne 0) { throw "step failed: $Name (exit $LASTEXITCODE)" }
}

function Skip-Step {
    param([string]$Name, [string]$Why)
    $script:Step++
    Say $Name
    Write-Host ("        SKIPPED ({0})" -f $Why)
}

Write-Host "======================================================================"
Write-Host " SOC Co-pilot -- full reproduction"
Write-Host (" dry-run={0}  api={1}  kaggle={2}  skip-heavy={3}" -f `
            [int]$DryRun.IsPresent, [int]$IncludeApi.IsPresent, `
            [int]$IncludeKaggle.IsPresent, [int]$SkipHeavy.IsPresent)
Write-Host (" expected runtime with these flags: {0}" -f $(if ($SkipHeavy) { '~1-2 h' } else { '~6-12 h' }))
Write-Host "======================================================================"

# --- Step 0-2: integrity, environment, tests -------------------------------
Invoke-Step 'Data integrity (SHA-256 against INTEGRITY_MANIFEST.json)' @('scripts/verify_data_integrity.py')
Invoke-Step 'Environment check' @('-c', "import sklearn, numpy, scipy, pandas; print('deps ok')")
Invoke-Step 'Baseline test suite' @('-m', 'pytest', 'tests/', '-q')

# --- Step 3: experiments, in dependency order ------------------------------
Invoke-Step 'M2.1 leakage: incident-level audit'      @('experiments/incident_leakage_audit.py')
Invoke-Step 'M2.1 leakage: grouped-split baseline'    @('experiments/grouped_split_baseline.py')
Invoke-Step 'M2.1 leakage: 7-seed split-method delta' @('experiments/m2_1_splitmethod_5seeds.py')
Invoke-Step 'M2.1 leakage: historical eval overlap'   @('experiments/m2_1_historical_eval_overlap.py')

if ($IncludeKaggle) {
    Invoke-Step 'M2.2 third-party Kaggle reproduction'     @('experiments/kaggle_repro/kaggle_notebook_1.py')
    Invoke-Step 'M2.2 third-party Kaggle reproduction (2)' @('experiments/kaggle_repro/kaggle_notebook_2.py')
} else {
    Skip-Step 'M2.2 third-party Kaggle reproduction'     'needs -IncludeKaggle and Kaggle auth'
    Skip-Step 'M2.2 third-party Kaggle reproduction (2)' 'needs -IncludeKaggle and Kaggle auth'
}

Invoke-Step 'M2.3 incident-grouped model deployment' @('experiments/m2_3_deploy_grouped_model.py')

if ($SkipHeavy) {
    Skip-Step 'M2.4 seven-classifier suite'  'HEAVY; -SkipHeavy set'
    Skip-Step 'Classifier improvement study' 'HEAVY; -SkipHeavy set'
} else {
    Invoke-Step 'M2.4 seven-classifier suite (HEAVY)'  @('experiments/m2_4_classifier_suite.py')
    Invoke-Step 'Classifier improvement study (HEAVY)' @('experiments/classifier_improvement_study.py')
}

Invoke-Step 'M3.1 build injection benchmark v1.0' @('experiments/m3_1_generate_benchmark.py')
Invoke-Step 'M3.2 heuristic detectors'            @('experiments/m3_2_heuristic_detectors.py')
Invoke-Step 'M3.1 blinded rater sheets'           @('experiments/m3_1_build_rating_worksheet.py')

if ($IncludeApi) {
    Invoke-Step 'M3.2 learned detectors (L1 + live Groq L2/L3)' @('experiments/m3_2_learned_detectors.py', '--detector', 'all')
} else {
    # L2 and L3 are live Groq calls; only L1 reproduces offline.
    Invoke-Step 'M3.2 learned detectors (L1, offline only)' @('experiments/m3_2_learned_detectors.py', '--detector', 'l1')
}

Invoke-Step 'M3.2 detector x family matrix'  @('experiments/m3_2_build_detector_matrix.py')

# M3.1 kappa needs two returned human rating sheets (issue #35).
$RaterA = 'experiments/results/m3_1_rating_sheet_raterA_completed.csv'
$RaterB = 'experiments/results/m3_1_rating_sheet_raterB_completed.csv'
if ((Test-Path $RaterA) -and (Test-Path $RaterB)) {
    Invoke-Step 'M3.1 inter-rater agreement' @('experiments/m3_1_interrater_kappa.py', '--rater-a', $RaterA, '--rater-b', $RaterB)
} else {
    Skip-Step 'M3.1 inter-rater agreement' "needs both completed rating sheets at $RaterA and $RaterB"
}
Invoke-Step 'Held-out GUIDE_Test evaluation' @('experiments/guide_test_holdout_eval.py')
Invoke-Step 'Paired RF vs LLM control'       @('experiments/rf_vs_llm_control.py')
Invoke-Step 'Guardrail layer evaluation'     @('experiments/guardrail_layer_eval.py')
Invoke-Step 'ROC / AUC analysis'             @('experiments/roc_auc_analysis.py')
Invoke-Step 'Verdict invariance check'       @('experiments/verdict_invariance_check.py')

# --- Step 4: statistics and manifests --------------------------------------
Invoke-Step 'M6.1 effect sizes and multiplicity' @('experiments/m6_1_effect_sizes.py')
Invoke-Step 'M6.3 bootstrap CI backfill'         @('experiments/m6_3_bootstrap_ci_backfill.py')
Invoke-Step 'M6.1 figure/table manifest'         @('experiments/m6_1_build_manifest.py')
Invoke-Step 'M6.1 statistical compliance audit'  @('experiments/m6_1_compliance_audit.py')

# --- Step 5: collect, then verify ------------------------------------------
$script:Step++
Say ("Collecting artifacts into {0}/" -f $OUT)
if ($DryRun) {
    Write-Host ("        would copy experiments/results/*.json and *.csv -> {0}/" -f $OUT)
} else {
    New-Item -ItemType Directory -Force -Path $OUT | Out-Null
    Copy-Item 'experiments/results/*.json' $OUT -ErrorAction SilentlyContinue
    Copy-Item 'experiments/results/*.csv'  $OUT -ErrorAction SilentlyContinue
    Copy-Item 'PAPER_FIGURE_MANIFEST.md','docs/statistical_compliance.md',
              'docs/ci_backfill_changes_for_paper.md' $OUT -ErrorAction SilentlyContinue
    Write-Host ("        {0} files collected" -f (Get-ChildItem $OUT).Count)
}

Invoke-Step 'M6.3 paper-claims regression suite' `
    @('-m', 'pytest', 'tests/test_paper_claims.py', 'tests/test_reported_numbers.py',
      'tests/test_manifest_integrity.py', '-q')

Write-Host ""
Write-Host "======================================================================"
if ($DryRun) {
    Write-Host (" DRY RUN COMPLETE -- {0} steps planned, nothing executed" -f $script:Step)
} else {
    Write-Host (" REPRODUCTION COMPLETE -- all {0} steps passed" -f $script:Step)
    Write-Host (" Artifacts: {0}/    Manifest: PAPER_FIGURE_MANIFEST.md" -f $OUT)
}
Write-Host "======================================================================"
