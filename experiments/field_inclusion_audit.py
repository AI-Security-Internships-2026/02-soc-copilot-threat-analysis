# experiments/field_inclusion_audit.py
#
# M1.2 Part C (issue #30). Two questions about which fields the pipeline trusts.
#
# PART C1 -- Is DetectorId really numeric?
#   src/agent/schema_guardrail.py treats AlertTitle and DetectorId as numeric ID
#   fields and blocks an alert whose value for either is non-numeric. That is a
#   security control: it is what stops a prompt-injection payload arriving in a
#   field the LLM will later read. The claim was verified for AlertTitle but
#   asserted for DetectorId. If DetectorId legitimately carries free text
#   anywhere in GUIDE, the guardrail produces false blocks on real traffic.
#   This samples every distinct value in a large slice and checks.
#
# PART C2 -- Are the target-adjacent fields in the feature matrix, and what are
#            they worth?
#   LastVerdict and SuspicionLevel are analyst/product verdicts about the same
#   alert the model is grading. They are flagged in the Limitations as
#   potentially leaky, but nobody had checked whether they are in the deployed
#   feature matrix, nor measured what removing them costs. Documenting a
#   suspicion is weaker than measuring it, so this ablates them and reports the
#   delta on the held-out split -- the only split where the answer is not itself
#   contaminated by incident-level leakage.
#
# usage (from repo root, offline, ~10 minutes):
#   venv/bin/python experiments/field_inclusion_audit.py
#   venv/bin/python experiments/field_inclusion_audit.py --skip-ablation   # C1 only

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score

from src.agent.fallback_classifier import _load_model
from src.agent.schema_guardrail import EXPECTED_NUMERIC_FIELDS
from src.data.schema import TARGET_COLUMN, TARGET_CLASSES
from src.models.decision import predict_labels

TRAIN_PATH = Path("datasets/GUIDE_train.csv")
TEST_SAMPLE = Path("experiments/results/evaluation_samples/guide_test_balanced_5000_per_class_seed_42.csv")
OUTPUT_PATH = Path("experiments/results/field_inclusion_audit.json")

AUDIT_ROWS = 500_000
TRAIN_ROWS = 100_000          # the deployed model's slice size
LEAKY_FIELDS = ["LastVerdict", "SuspicionLevel"]
SEED = 42


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _is_numeric(value) -> bool:
    """Would the schema guardrail accept this value as a numeric ID?"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return True          # absent, not malformed -- the guardrail skips it
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def audit_numeric_fields(df: pd.DataFrame) -> dict:
    out = {}
    for field in sorted(EXPECTED_NUMERIC_FIELDS):
        if field not in df.columns:
            out[field] = {"present": False}
            continue
        values = df[field]
        distinct = values.dropna().unique()
        offenders = [v for v in distinct if not _is_numeric(v)]
        out[field] = {
            "present": True,
            "rows_scanned": int(len(values)),
            "distinct_values": int(len(distinct)),
            "non_numeric_distinct_values": int(len(offenders)),
            "non_numeric_rate_over_distinct": round(len(offenders) / max(len(distinct), 1), 6),
            "examples_of_non_numeric": [str(v)[:80] for v in offenders[:10]],
            "all_parse_as_numeric": not offenders,
        }
    return out


def _prepare(df: pd.DataFrame, model, encoders, drop: list[str] | None = None):
    """Encode a frame the same way the deployed classifier's features are built."""
    features = [f for f in model.feature_names_in_ if not drop or f not in drop]
    frame = pd.DataFrame(index=df.index)
    for column in features:
        raw = df[column] if column in df.columns else pd.Series([None] * len(df), index=df.index)
        encoder = encoders.get(column)
        if encoder is None:
            frame[column] = pd.to_numeric(raw, errors="coerce").fillna(-1)
            continue
        mapping = {label: code for code, label in enumerate(encoder.classes_)}
        frame[column] = raw.astype(str).map(mapping).fillna(-1).astype(int)
    return frame[features]


def ablate_leaky_fields() -> dict:
    """Retrain with and without LastVerdict/SuspicionLevel; score both held out."""
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    print(f"reading {TRAIN_ROWS:,} training rows...")
    train = pd.read_csv(TRAIN_PATH, nrows=TRAIN_ROWS, low_memory=False)
    train = train.dropna(subset=[TARGET_COLUMN])
    train = train[train[TARGET_COLUMN].isin(TARGET_CLASSES)]

    test = pd.read_csv(TEST_SAMPLE)
    y_test = test[TARGET_COLUMN]

    results = {}
    for arm, drop in (("with_leaky_fields", None), ("without_leaky_fields", LEAKY_FIELDS)):
        print(f"training arm '{arm}'...")
        X = _prepare(train, model, encoders, drop)
        forest = RandomForestClassifier(
            n_estimators=200, random_state=SEED, n_jobs=-1, class_weight=None
        )
        forest.fit(X, train[TARGET_COLUMN])

        y_pred = predict_labels(forest, _prepare(test, model, encoders, drop))
        results[arm] = {
            "n_features": int(X.shape[1]),
            "dropped": drop or [],
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "macro_f1": round(float(f1_score(y_test, y_pred, average="macro", zero_division=0)), 4),
            "n_test": int(len(test)),
        }
        print(f"  accuracy {results[arm]['accuracy']}  macro F1 {results[arm]['macro_f1']}")

    a, b = results["with_leaky_fields"], results["without_leaky_fields"]
    results["delta"] = {
        "accuracy": round(a["accuracy"] - b["accuracy"], 4),
        "macro_f1": round(a["macro_f1"] - b["macro_f1"], 4),
        "reading": (
            "Positive means the target-adjacent fields are helping. Because both "
            "arms are scored on the held-out GUIDE_Test split, this is what the "
            "fields are worth on alerts from incidents the model never saw -- "
            "not an artefact of the row-level split."
        ),
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Field inclusion audit (M1.2 Part C).")
    parser.add_argument("--skip-ablation", action="store_true", help="run Part C1 only")
    parser.add_argument("--audit-rows", type=int, default=AUDIT_ROWS)
    args = parser.parse_args()

    if not TRAIN_PATH.exists():
        raise SystemExit(f"{TRAIN_PATH} is required for this audit; see datasets/README.md.")

    print(f"scanning {args.audit_rows:,} rows of {TRAIN_PATH} for numeric-field violations...")
    columns = sorted(EXPECTED_NUMERIC_FIELDS)
    df = pd.read_csv(TRAIN_PATH, nrows=args.audit_rows, usecols=columns, low_memory=False)
    numeric = audit_numeric_fields(df)
    for field, r in numeric.items():
        if r.get("present"):
            print(f"  {field}: {r['distinct_values']:,} distinct, "
                  f"{r['non_numeric_distinct_values']} non-numeric")

    artifact = _load_model()
    deployed_features = list(artifact["model"].feature_names_in_)

    output = {
        "experiment": "Field inclusion audit: numeric-ID guardrail coverage, and target-adjacent feature ablation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "issue": "#30 (M1.2) Parts C1 and C2",
        "part_c1_numeric_field_audit": {
            "source": str(TRAIN_PATH),
            "rows_scanned": int(args.audit_rows),
            "fields_the_schema_guardrail_requires_to_be_numeric": columns,
            "results": numeric,
        },
        "part_c2_feature_inclusion": {
            "deployed_feature_count": len(deployed_features),
            "deployed_features": deployed_features,
            "target_adjacent_fields": LEAKY_FIELDS,
            "in_feature_matrix": {f: f in deployed_features for f in LEAKY_FIELDS},
            "DetectorId_in_feature_matrix": "DetectorId" in deployed_features,
        },
    }

    if not args.skip_ablation:
        output["part_c2_ablation"] = ablate_leaky_fields()

    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
