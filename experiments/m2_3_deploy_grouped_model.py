# experiments/m2_3_deploy_grouped_model.py
#
# M2.3 PART B (issue #33). Closes two paper Limitations bullets: (A) the
# deployed model retains a row-level split, 2.83 accuracy points lost to
# split-method inflation alone (M2.1 PART A); (B) M2.4's winning
# configuration was measured but never deployed. This script retrains
# M2.4's selected model with an incident-level GroupShuffleSplit -- Protocol
# B, EVAL_PROTOCOL.md -- and re-scores it on the same three evaluation
# samples the paper's headline numbers already use, so the deltas are
# apples-to-apples rather than a new number against an old one.
#
# Gated on experiments/results/m2_4_best_model_selection.json existing: this
# script retrains M2.4's actual selected model/config, not a hardcoded
# guess at what M2.4 would pick.
#
# Deliberately does NOT touch experiments/results/baseline_model.joblib or
# any deployed inference path. The new artifact is written only to
# models/best_grouped_classifier.joblib (gitignored, same as
# baseline_model.joblib -- see .gitignore's M2.4 section). Whether it ever
# becomes the deployed model is docs/m2-3-deploy-decision-memo.md's decision,
# made with these numbers as evidence, not this script's.
#
# The fourth re-evaluation the issue asks for -- control-node ablation arms
# (a) explanation-on / (b) explanation-off producing identical verdicts --
# is NOT re-run against a swapped model here. That invariant is
# architectural (explain_with_llm structurally cannot write
# predicted_label/confidence, src/agent/nodes.py) and does not depend on
# which classifier backs _load_model(); control_node_ablation.py already
# proved it row-for-row. Re-running the live graph against an unreleased
# candidate artifact would risk mutating shared state for no new evidence.
#
# usage (from repo root, after experiments/m2_4_classifier_suite.py --mode heldout has run):
#   venv/bin/python experiments/m2_3_deploy_grouped_model.py

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from experiments.classifier_improvement_study import accuracy, macro_f1, score_holdout
from experiments.m2_4_classifier_suite import (
    HELDOUT_TRAIN_ROWS,
    SEED,
    TRAIN_DATA_PATH,
    apply_onehot,
    build_onehot,
    check_deploy_compatibility,
    fit_model,
    make_estimator,
    score_holdout_onehot,
)
from experiments.streaming_encode import load_encoded
from src.data.schema import TARGET_CLASSES, TARGET_COLUMN
from src.models.decision import predict_labels

SELECTION_PATH = Path("experiments/results/m2_4_best_model_selection.json")
OUTPUT_PATH = Path("experiments/results/m2_3_grouped_deployed.json")
MODEL_PATH = Path("models/best_grouped_classifier.joblib")
DECISION_MEMO_PATH = Path("docs/m2-3-deploy-decision-memo.md")

CACHE_DIR = Path("experiments/results/evaluation_samples")
A4_PIPELINE_SAMPLE_PATH = CACHE_DIR / "guide_balanced_333_per_class_seed_42.csv"
A4_PIPELINE_REFERENCE_ACCURACY = 0.7347  # guide_test_holdout_eval.json:train_sampled_999_rf_primary_pipeline
HELDOUT_REFERENCE_ACCURACY = 0.6998  # guide_test_holdout_eval.json:test_holdout_15000

VAL_SIZE = 0.2


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def score_cached_sample(model, encoders, feature_names, is_onehot, top_categories, path: Path) -> dict:
    df = pd.read_csv(path)
    if is_onehot:
        result = score_holdout_onehot(model, encoders, top_categories, feature_names, df)
    else:
        result = score_holdout(model, encoders, feature_names, df)
    result.pop("_y_true", None)
    result.pop("_y_pred", None)
    return result


def main() -> None:
    if not SELECTION_PATH.exists():
        raise SystemExit(
            f"{SELECTION_PATH} not found. Run experiments/m2_4_classifier_suite.py --mode heldout "
            "first -- this script retrains M2.4's actual selected model, not a guess at one."
        )
    selection = json.loads(SELECTION_PATH.read_text())
    model_id = selection["selected"]
    print(f"M2.4 selected: {model_id} ({selection.get('selection_reason')})", flush=True)

    if not TRAIN_DATA_PATH.exists():
        raise SystemExit(f"{TRAIN_DATA_PATH} not found.")

    print(f"loading the same {HELDOUT_TRAIN_ROWS:,}-row training slice M2.4's heldout mode used...", flush=True)
    X, y, groups, encoders = load_encoded(TRAIN_DATA_PATH, HELDOUT_TRAIN_ROWS)
    cat_cols = list(encoders.keys())
    feature_names = list(X.columns)

    is_onehot = model_id == "M3b"
    top_categories = None
    if is_onehot:
        X, top_categories = build_onehot(X, encoders)
        feature_names = list(X.columns)

    # --- Protocol B: GroupShuffleSplit on (OrgId, IncidentId) ------------
    gss = GroupShuffleSplit(n_splits=1, test_size=VAL_SIZE, random_state=SEED)
    train_idx, val_idx = next(gss.split(X, y, groups=groups))
    train_incidents = set(groups[train_idx])
    val_incidents = set(groups[val_idx])
    overlap = train_incidents & val_incidents
    assert len(overlap) == 0, (
        f"{len(overlap)} incidents cross the train/val split boundary -- Protocol B requires zero."
    )
    print(f"train={len(train_idx):,} val={len(val_idx):,}, 0 incidents cross the boundary (verified)", flush=True)

    # --- (b) fit on TRAIN only, VAL used as a monitoring metric ----------
    # None of M1-M6's factories wire up true early stopping against a
    # validation set (see make_estimator() in m2_4_classifier_suite.py) --
    # this is the substantive equivalent the issue's "early-stopping checks
    # ONLY" step gets here: a monitoring number, not a training-time gate.
    estimator, kind = make_estimator(model_id, cat_cols)
    fitted_train_only, seconds_train = fit_model(
        model_id, estimator, kind, X.iloc[train_idx], y.iloc[train_idx], cat_cols
    )
    val_pred = predict_labels(fitted_train_only, X.iloc[val_idx])
    val_accuracy = accuracy(y.iloc[val_idx], val_pred)
    val_macro_f1 = macro_f1(y.iloc[val_idx], val_pred)
    print(f"train-only fit: val accuracy={val_accuracy:.4f} macro_f1={val_macro_f1:.4f} ({seconds_train}s)", flush=True)

    # --- (c) refit on 100% train+val for the deployable artifact ---------
    estimator_full, kind_full = make_estimator(model_id, cat_cols)
    fitted_full, seconds_full = fit_model(model_id, estimator_full, kind_full, X, y, cat_cols)
    print(f"refit on 100% train+val ({len(X):,} rows) in {seconds_full}s", flush=True)

    # CatBoost compatibility shim (see the M2.4 deploy-compatibility note):
    # a plain attribute assignment is enough to satisfy
    # fallback_classifier.py's hasattr(model, "feature_names_in_") check and
    # give _to_feature_frame() the column order it needs to reindex against.
    names_ok = hasattr(fitted_full, "feature_names_in_") and list(fitted_full.feature_names_in_) == feature_names
    if not names_ok:
        try:
            fitted_full.feature_names_in_ = np.array(feature_names, dtype=object)
            names_ok = True
            shim_applied = True
        except Exception as exc:
            shim_applied = False
            print(f"  WARNING: could not apply the feature_names_in_ shim: {exc}", flush=True)
    else:
        shim_applied = False

    # --- 3 re-evaluations on the paper's existing cached samples ---------
    print("scoring on the GUIDE_Test 15K held-out sample...", flush=True)
    from experiments.classifier_improvement_study import load_holdout

    heldout = load_holdout()
    heldout_result = (
        score_holdout_onehot(fitted_full, encoders, top_categories, feature_names, heldout)
        if is_onehot
        else score_holdout(fitted_full, encoders, feature_names, heldout)
    )
    heldout_result.pop("_y_true", None)
    heldout_result.pop("_y_pred", None)

    a4_result = None
    if A4_PIPELINE_SAMPLE_PATH.exists():
        print("scoring on the 999-alert A4 pipeline sample...", flush=True)
        a4_result = score_cached_sample(
            fitted_full, encoders, feature_names, is_onehot, top_categories, A4_PIPELINE_SAMPLE_PATH
        )

    output = {
        "experiment": (
            "M2.3 PART B: retrain M2.4's selected classifier with an incident-level "
            "GroupShuffleSplit (Protocol B) and re-score on the paper's existing evaluation samples"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "protocol": "ACCEPTABLE (internal split) / PREFERRED (GUIDE_Test scoring)",
        "selected_model_id": model_id,
        "selection_source": str(SELECTION_PATH),
        "train_rows": HELDOUT_TRAIN_ROWS,
        "split": {
            "rule": "GroupShuffleSplit(test_size=0.2, random_state=42) on (OrgId, IncidentId)",
            "n_train": int(len(train_idx)),
            "n_val": int(len(val_idx)),
            "incidents_crossing_boundary": len(overlap),
        },
        "train_only_val_monitoring": {
            "n": int(len(val_idx)),
            "accuracy": round(val_accuracy, 4),
            "macro_f1": round(val_macro_f1, 4),
            "train_seconds": seconds_train,
            "note": "monitoring metric, not an early-stopping gate -- see module docstring",
        },
        "deploy_compatibility": {
            **check_deploy_compatibility(model_id, names_ok),
            "shim_applied": shim_applied,
        },
        "refit_full_train_seconds": seconds_full,
        "new_heldout_15000": heldout_result,
        "delta_vs_0_6998": round(heldout_result["accuracy"] - HELDOUT_REFERENCE_ACCURACY, 4),
        "new_a4_pipeline_999": a4_result,
        "delta_vs_0_7347": (
            round(a4_result["accuracy"] - A4_PIPELINE_REFERENCE_ACCURACY, 4) if a4_result else None
        ),
        "control_node_arms_a_b_invariant": {
            "checked": False,
            "reason": (
                "Architectural invariant (explain_with_llm cannot write predicted_label/confidence), "
                "not model-dependent -- already proven row-for-row in control_node_ablation.json. "
                "Not re-run against this candidate artifact; see module docstring."
            ),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nsaved to {OUTPUT_PATH}")

    if names_ok:
        import joblib

        MODEL_PATH.parent.mkdir(exist_ok=True)
        joblib.dump({"model": fitted_full, "encoders": encoders, "feature_names": feature_names}, MODEL_PATH)
        print(f"candidate artifact saved to {MODEL_PATH} (NOT the deployed baseline_model.joblib)")
    else:
        print(f"candidate artifact NOT saved -- {model_id} failed the deploy-compatibility check")

    print(f"\nnew held-out accuracy: {heldout_result['accuracy']:.4f} "
          f"(delta {output['delta_vs_0_6998']:+.4f} vs deployed 0.6998)")
    if a4_result:
        print(f"new A4-pipeline accuracy: {a4_result['accuracy']:.4f} "
              f"(delta {output['delta_vs_0_7347']:+.4f} vs deployed 0.7347)")
    print(f"\nSee {DECISION_MEMO_PATH} for the ADOPT vs KEEP decision.")


if __name__ == "__main__":
    main()
