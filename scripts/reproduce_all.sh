#!/usr/bin/env bash
# One-command reproduction of every experiment behind the paper (issue #45, M6.2).
#
# Typical runtime: ~6-12 hours on a CPU laptop with the default flags. The two
# heaviest stages are the classifier study (up to 2M training rows) and the
# held-out evaluations; both are marked HEAVY below.
#
#   ./scripts/reproduce_all.sh                 # offline-reproducible set
#   ./scripts/reproduce_all.sh --dry-run       # print the plan, run nothing
#   ./scripts/reproduce_all.sh --include-api   # + detectors needing OpenAI/Groq
#   ./scripts/reproduce_all.sh --include-kaggle
#   ./scripts/reproduce_all.sh --skip-heavy    # skip multi-hour stages
#
# Fails fast: the first non-zero exit stops the run. That is deliberate --
# a later stage reading a half-written result is worse than stopping.

set -euo pipefail

DRY_RUN=0; INCLUDE_API=0; INCLUDE_KAGGLE=0; SKIP_HEAVY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)        DRY_RUN=1 ;;
    --include-api)    INCLUDE_API=1 ;;
    --include-kaggle) INCLUDE_KAGGLE=1 ;;
    --skip-heavy)     SKIP_HEAVY=1 ;;
    --gpu)            export SOC_COPILOT_USE_GPU=1 ;;
    -h|--help)        sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg (try --help)" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
PY="venv/bin/python"
OUT="experiments/paper_ready"
STEP=0
TOTAL=28

say()  { printf '\n\033[1m[%2d/%2d] %s\033[0m\n' "$STEP" "$TOTAL" "$1"; }
run()  {
  STEP=$((STEP+1)); say "$1"; shift
  if [ "$DRY_RUN" = "1" ]; then printf '        would run: %s\n' "$*"; else "$@"; fi
}
skip() { STEP=$((STEP+1)); say "$1"; printf '        SKIPPED (%s)\n' "$2"; }

echo "======================================================================"
echo " SOC Co-pilot -- full reproduction"
echo " dry-run=$DRY_RUN  api=$INCLUDE_API  kaggle=$INCLUDE_KAGGLE  skip-heavy=$SKIP_HEAVY"
echo " expected runtime with these flags: $([ "$SKIP_HEAVY" = 1 ] && echo '~1-2 h' || echo '~6-12 h')"
echo "======================================================================"

# --- Step 0: the data must be the data every committed figure came from ----
run "Data integrity (SHA-256 against INTEGRITY_MANIFEST.json)" \
    $PY scripts/verify_data_integrity.py

# --- Step 1: environment ---------------------------------------------------
run "Environment check" $PY -c "import sklearn, numpy, scipy, pandas; print('deps ok')"

# --- Step 2: the suite must be green before anything is trusted ------------
run "Baseline test suite" $PY -m pytest tests/ -q

# --- Step 3: experiments, in dependency order ------------------------------
run "M2.1 leakage: incident-level audit"        $PY experiments/incident_leakage_audit.py
run "M2.1 leakage: grouped-split baseline"      $PY experiments/grouped_split_baseline.py
run "M2.1 leakage: 7-seed split-method delta"   $PY experiments/m2_1_splitmethod_5seeds.py
run "M2.1 leakage: historical eval overlap"     $PY experiments/m2_1_historical_eval_overlap.py

if [ "$INCLUDE_KAGGLE" = "1" ]; then
  run "M2.2 third-party Kaggle reproduction"    $PY experiments/kaggle_repro/kaggle_notebook_1.py
  run "M2.2 third-party Kaggle reproduction (2)" $PY experiments/kaggle_repro/kaggle_notebook_2.py
else
  skip "M2.2 third-party Kaggle reproduction" "needs --include-kaggle and Kaggle auth"
  skip "M2.2 third-party Kaggle reproduction (2)" "needs --include-kaggle and Kaggle auth"
fi

run "M2.3 incident-grouped model deployment"    $PY experiments/m2_3_deploy_grouped_model.py

if [ "$SKIP_HEAVY" = "1" ]; then
  skip "M2.4 seven-classifier suite" "HEAVY; --skip-heavy set"
  skip "Classifier improvement study" "HEAVY; --skip-heavy set"
else
  run "M2.4 seven-classifier suite (HEAVY)"     $PY experiments/m2_4_classifier_suite.py
  run "Classifier improvement study (HEAVY)"    $PY experiments/classifier_improvement_study.py
fi

run "M3.1 build injection benchmark v1.0"       $PY experiments/m3_1_generate_benchmark.py
run "M3.2 heuristic detectors"                  $PY experiments/m3_2_heuristic_detectors.py

if [ "$INCLUDE_API" = "1" ]; then
  run "M3.2 learned detectors (API)"            $PY experiments/m3_2_learned_detectors.py --include-api
else
  run "M3.2 learned detectors (offline only)"   $PY experiments/m3_2_learned_detectors.py
fi

run "M3.2 detector x family matrix"             $PY experiments/m3_2_build_detector_matrix.py
run "M3.1 inter-rater agreement"                $PY experiments/m3_1_interrater_kappa.py
run "Held-out GUIDE_Test evaluation"            $PY experiments/guide_test_holdout_eval.py
run "Paired RF vs LLM control"                  $PY experiments/rf_vs_llm_control.py
run "Guardrail layer evaluation"                $PY experiments/guardrail_layer_eval.py
run "ROC / AUC analysis"                        $PY experiments/roc_auc_analysis.py
run "Verdict invariance check"                  $PY experiments/verdict_invariance_check.py

# --- Step 4: statistics and manifests over everything above ----------------
run "M6.1 effect sizes and multiplicity"        $PY experiments/m6_1_effect_sizes.py
run "M6.3 bootstrap CI backfill"                $PY experiments/m6_3_bootstrap_ci_backfill.py
run "M6.1 figure/table manifest"                $PY experiments/m6_1_build_manifest.py
run "M6.1 statistical compliance audit"         $PY experiments/m6_1_compliance_audit.py

# --- Step 5: collect, then verify the claims still hold --------------------
STEP=$((STEP+1)); say "Collecting artifacts into $OUT/"
if [ "$DRY_RUN" = "1" ]; then
  printf '        would copy experiments/results/*.json and *.csv -> %s/\n' "$OUT"
else
  mkdir -p "$OUT"
  cp experiments/results/*.json experiments/results/*.csv "$OUT"/ 2>/dev/null || true
  cp PAPER_FIGURE_MANIFEST.md docs/statistical_compliance.md \
     docs/ci_backfill_changes_for_paper.md "$OUT"/ 2>/dev/null || true
  echo "        $(ls "$OUT" | wc -l | tr -d ' ') files collected"
fi

run "M6.3 paper-claims regression suite" \
    $PY -m pytest tests/test_paper_claims.py tests/test_reported_numbers.py \
                  tests/test_manifest_integrity.py -q

echo ""
echo "======================================================================"
if [ "$DRY_RUN" = "1" ]; then
  echo " DRY RUN COMPLETE -- $STEP steps planned, nothing executed"
else
  echo " REPRODUCTION COMPLETE -- all $STEP steps passed"
  echo " Artifacts: $OUT/    Manifest: PAPER_FIGURE_MANIFEST.md"
fi
echo "======================================================================"
