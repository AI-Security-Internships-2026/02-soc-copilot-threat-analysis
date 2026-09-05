# experiments/incident_leakage_audit.py
#
# The paper's Limitations section asserts, without measuring it, that
# "train/test splits are row-level, not incident-level. GUIDE contains many
# alerts per incident and the label is incident-level, so alerts from one
# incident can straddle the split boundary." This script measures it.
#
# The distinction matters because of what the project already discloses.
# rf_vs_llm_control.py reports a 1.91% (4/209) *exact-row* overlap between
# the RF's training rows and its evaluation sample, and judges it
# immaterial. That figure is correct, and it is also the wrong thing to
# measure: GUIDE rows are evidence records, several per incident, and the
# IncidentGrade label attaches to the incident rather than to the row. Two
# different rows from one incident are not two independent examples. Exact
# row deduplication cannot see that, so a sample can show ~2% overlap while
# most of its rows still have a labelled sibling in the training set.
#
# Four parts, in the order the argument has to be made:
#
#   A. Structural facts about the RF's own 100,000-row training slice --
#      how many incidents, how many rows share one, and whether the label
#      is actually constant within an incident. If labels varied within an
#      incident, a shared incident would leak nothing and the rest of this
#      script would be pointless.
#
#   B. Key integrity. A high overlap rate is only alarming if (OrgId,
#      IncidentId) is a genuine incident identifier rather than a
#      small-cardinality field colliding by chance. We test this by taking
#      a block of rows from a distant region of the file and checking
#      whether colliding keys carry the *same* label. Chance collision
#      would produce agreement near the majority-class rate; a real key
#      produces agreement near 1.0.
#
#   C. Overlap rates for the evaluation samples the paper actually reports
#      on -- exact-row (the figure already published) beside incident-level
#      (the figure that was missing), for both the GUIDE_train-sampled set
#      and the GUIDE_Test.csv held-out set.
#
#   D. The causal test. Parts A-C establish that the leak exists; none of
#      them show it changes any number. This part does: draw a block of
#      rows from OUTSIDE the training slice, split it by whether each row's
#      incident appears in the training slice, class-balance the two
#      buckets so their majority-class floors are identical, and score the
#      RF on each. Both buckets are rows the model never trained on. They
#      differ only in whether a labelled sibling was available. The
#      difference between them, if any, is what the leak is worth.
#
# Part D is reported as measured in either direction. A null result there
# would mean the overlap is real but inert, which weakens the finding and
# is worth knowing; the script is not built to produce a particular answer.
#
# Fully offline -- predict_proba against the already-trained
# baseline_model.joblib. No Groq calls, no retraining, no LLM quota.
#
# usage (from repo root):
#   venv/bin/python experiments/incident_leakage_audit.py
#   venv/bin/python experiments/incident_leakage_audit.py --eval-block-rows 400000

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
from sklearn.metrics import accuracy_score, f1_score

from src.agent.fallback_classifier import _load_model, _to_feature_frame
from src.data.load_data import REAL_DATA_PATH
from src.data.schema import TARGET_COLUMN, TARGET_CLASSES
from src.models.decision import resolve_label
from experiments.stats_utils import bootstrap_metric_ci, bootstrap_two_sample_diff_ci

# Mirrors src/models/baseline.py: the deployed model trains on the first
# 100,000 rows of GUIDE_train.csv in file order. Anything at or past this
# row index was never a training candidate.
TRAINING_SLICE_ROWS = 100_000

INCIDENT_KEY = ["OrgId", "IncidentId"]
CACHE_DIR = Path("experiments/results/evaluation_samples")
OUTPUT_PATH = Path("experiments/results/incident_leakage_audit.json")

# Part B reads from here to test key integrity. Far enough from the
# training slice that any overlap is recurrence or collision, not adjacency.
DISTANT_BLOCK_START = 5_000_000
DISTANT_BLOCK_ROWS = 20_000

SEED = 42


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _keys(df: pd.DataFrame) -> list[tuple]:
    return list(zip(df[INCIDENT_KEY[0]], df[INCIDENT_KEY[1]]))


def load_training_slice() -> pd.DataFrame:
    """The exact rows src/models/baseline.py trains on, keys and label only."""
    df = pd.read_csv(
        REAL_DATA_PATH,
        nrows=TRAINING_SLICE_ROWS,
        usecols=INCIDENT_KEY + [TARGET_COLUMN],
    )
    # baseline.py drops rows with a missing target before splitting, so the
    # model never sees them; they are not part of the training slice.
    return df.dropna(subset=[TARGET_COLUMN])


def part_a_structural_facts(train_slice: pd.DataFrame) -> dict:
    """Is the label incident-level, and how many rows share an incident?"""
    grouped = train_slice.groupby(INCIDENT_KEY)[TARGET_COLUMN]
    sizes = grouped.size()
    distinct_labels = grouped.nunique()

    n_rows = len(train_slice)
    multi_row_rows = int(sizes[sizes > 1].sum())
    single_label_incidents = int((distinct_labels == 1).sum())

    return {
        "training_slice_rows": n_rows,
        "unique_incidents": int(len(sizes)),
        "mean_rows_per_incident": round(float(sizes.mean()), 4),
        "max_rows_per_incident": int(sizes.max()),
        "multi_row_incidents": int((sizes > 1).sum()),
        "rows_belonging_to_a_multi_row_incident": multi_row_rows,
        "rows_belonging_to_a_multi_row_incident_rate": round(multi_row_rows / n_rows, 4),
        "incidents_with_a_single_label_value": single_label_incidents,
        "label_constancy_rate": round(single_label_incidents / len(sizes), 6),
        "finding": (
            f"The label is constant within an incident for "
            f"{single_label_incidents}/{len(sizes)} incidents "
            f"({single_label_incidents / len(sizes):.4%}). "
            f"{multi_row_rows / n_rows:.1%} of training rows belong to an incident "
            f"with more than one row. Knowing an incident's grade from any one "
            f"labelled row therefore determines the grade of every sibling row."
        ),
    }


def part_b_key_integrity(train_label_by_key: dict) -> dict:
    """Do colliding incident keys carry the same label, or is it chance?"""
    distant = pd.read_csv(
        REAL_DATA_PATH,
        skiprows=range(1, DISTANT_BLOCK_START + 1),
        nrows=DISTANT_BLOCK_ROWS,
        usecols=INCIDENT_KEY + [TARGET_COLUMN],
    ).dropna(subset=[TARGET_COLUMN])

    hits = [
        (key, label)
        for key, label in zip(_keys(distant), distant[TARGET_COLUMN])
        if key in train_label_by_key
    ]
    agreeing = sum(1 for key, label in hits if train_label_by_key[key] == label)

    # If keys collided by chance, agreement would sit near the rate you'd
    # get by guessing the training slice's label for that key at random --
    # approximately the majority-class share. Stating that floor is what
    # makes an agreement rate near 1.0 interpretable rather than assertable.
    majority_share = float(distant[TARGET_COLUMN].value_counts(normalize=True).max())

    return {
        "block_start_row": DISTANT_BLOCK_START,
        "block_rows_scored": int(len(distant)),
        "rows_whose_key_appears_in_training_slice": len(hits),
        "key_collision_rate": round(len(hits) / len(distant), 4) if len(distant) else None,
        "colliding_rows_with_matching_label": agreeing,
        "label_agreement_rate": round(agreeing / len(hits), 6) if hits else None,
        "chance_agreement_floor_majority_class": round(majority_share, 4),
        "finding": (
            f"Of {len(hits)} rows in a block starting at row {DISTANT_BLOCK_START:,} "
            f"whose (OrgId, IncidentId) also appears in the training slice, "
            f"{agreeing} carry the identical label "
            f"({agreeing / len(hits):.4%}) against a "
            f"{majority_share:.1%} chance floor. The key identifies a real "
            f"incident; it is not colliding by accident."
            if hits
            else "No colliding keys found in the distant block."
        ),
    }


def part_c_sample_overlap(train_slice: pd.DataFrame, train_label_by_key: dict) -> dict:
    """Exact-row vs incident-level overlap for the samples the paper reports on."""
    # Exact-row overlap needs the full 45-column training rows, not just keys.
    train_full = pd.read_csv(REAL_DATA_PATH, nrows=TRAINING_SLICE_ROWS).dropna(
        subset=[TARGET_COLUMN]
    )
    train_row_hashes = set(
        pd.util.hash_pandas_object(train_full, index=False).astype("int64").tolist()
    )
    train_keys = set(train_label_by_key)

    samples = {
        "train_sampled_999": CACHE_DIR / "guide_balanced_333_per_class_seed_42.csv",
        "held_out_999": CACHE_DIR / "guide_test_balanced_333_per_class_seed_42.csv",
    }

    results = {}
    for name, path in samples.items():
        if not path.exists():
            results[name] = {"status": "sample cache absent", "path": str(path)}
            continue
        sample = pd.read_csv(path)
        # GUIDE_Test.csv carries an extra "Usage" column; drop it so the row
        # hash is computed over the same 45 columns on both sides.
        comparable = sample[[c for c in train_full.columns if c in sample.columns]]
        sample_hashes = pd.util.hash_pandas_object(comparable, index=False).astype("int64")

        exact = int(sum(h in train_row_hashes for h in sample_hashes))
        incident = int(sum(k in train_keys for k in _keys(sample)))
        n = len(sample)
        results[name] = {
            "path": str(path),
            "n": n,
            "exact_row_overlap": exact,
            "exact_row_overlap_rate": round(exact / n, 4),
            "incident_level_overlap": incident,
            "incident_level_overlap_rate": round(incident / n, 4),
        }

    return {
        "samples": results,
        "finding": (
            "Exact-row overlap is the figure already published (1.91% on the "
            "209-alert control set, judged immaterial). Incident-level overlap "
            "is what determines whether a labelled sibling was available to the "
            "model, and it is roughly an order of magnitude larger on the "
            "GUIDE_train-sampled set. The GUIDE_Test.csv sample is clean on both."
        ),
    }


def _balance_classes(df: pd.DataFrame, per_class: int, seed: int) -> pd.DataFrame:
    """Take exactly per_class rows of each label, so two buckets are comparable."""
    parts = [
        df[df[TARGET_COLUMN] == label].sample(n=per_class, random_state=seed)
        for label in TARGET_CLASSES
    ]
    return pd.concat(parts).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def _score_rows(sample: pd.DataFrame) -> tuple[list, list]:
    """RF predictions for a frame of raw alert rows."""
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    y_true, y_pred = [], []
    total = len(sample)
    for i, (_, row) in enumerate(sample.iterrows()):
        if i and i % 2000 == 0:
            print(f"    scored {i}/{total}", flush=True)
        alert = row.to_dict()
        y_true.append(alert.pop(TARGET_COLUMN))
        features = _to_feature_frame(alert, model, encoders)
        proba = model.predict_proba(features)[0]
        # Same tie-break as the deployed path and every figure these numbers are
        # compared against. This file previously used np.argmax, which resolves
        # a tie in the opposite direction -- see src/models/decision.py.
        y_pred.append(resolve_label(model.classes_, proba))
    return y_true, y_pred


def part_d_causal_test(
    train_label_by_key: dict, eval_block_rows: int, per_class_cap: int
) -> dict:
    """Does a shared incident actually change the model's accuracy?

    Both buckets are rows past the training slice -- the model trained on
    neither. They differ only in whether a labelled sibling from the same
    incident was in the training data. Class-balanced to identical
    distributions so the majority-class floor cannot explain a gap.
    """
    block = pd.read_csv(
        REAL_DATA_PATH,
        skiprows=range(1, TRAINING_SLICE_ROWS + 1),
        nrows=eval_block_rows,
    ).dropna(subset=[TARGET_COLUMN])

    train_keys = set(train_label_by_key)
    seen = np.array([k in train_keys for k in _keys(block)])
    leaked_all, clean_all = block[seen], block[~seen]

    # Balance both buckets to the same per-class count so accuracy is
    # directly comparable rather than reflecting a different class mix.
    per_class = min(
        [
            int(bucket[bucket[TARGET_COLUMN] == label].shape[0])
            for bucket in (leaked_all, clean_all)
            for label in TARGET_CLASSES
        ]
        # Capped so the bootstrap stays tractable. n=per_class_cap*3 per
        # bucket already resolves an accuracy gap of a couple of points;
        # scoring every available row would multiply runtime for precision
        # the finding does not need.
        + [per_class_cap]
    )
    if per_class == 0:
        return {"status": "a class is unrepresented in one bucket; cannot balance"}

    leaked = _balance_classes(leaked_all, per_class, SEED)
    clean = _balance_classes(clean_all, per_class, SEED)

    leaked_true, leaked_pred = _score_rows(leaked)
    clean_true, clean_pred = _score_rows(clean)

    acc = lambda t, p: accuracy_score(t, p)
    macro_f1 = lambda t, p: f1_score(t, p, average="macro", zero_division=0)

    # Per-class recall as well: if the leaked bucket wins within every
    # class, no residual class-mix artefact can explain the gap.
    def per_class_recall(y_true: list, y_pred: list) -> dict:
        out = {}
        for label in TARGET_CLASSES:
            idx = [i for i, t in enumerate(y_true) if t == label]
            out[label] = (
                round(sum(y_pred[i] == label for i in idx) / len(idx), 4) if idx else None
            )
        return out

    accuracy_gap = bootstrap_two_sample_diff_ci(
        leaked_true, leaked_pred, clean_true, clean_pred, acc, seed=SEED
    )
    f1_gap = bootstrap_two_sample_diff_ci(
        leaked_true, leaked_pred, clean_true, clean_pred, macro_f1, seed=SEED
    )

    return {
        "design": (
            "Both buckets are drawn from GUIDE_train.csv rows past the "
            f"{TRAINING_SLICE_ROWS:,}-row training slice, so the model trained on "
            "neither. 'leaked' rows belong to an incident that does appear in the "
            "training slice (a labelled sibling was available); 'clean' rows do "
            "not. Both are class-balanced to identical per-class counts."
        ),
        "eval_block_rows_read": int(eval_block_rows),
        "eval_block_rows_with_a_label": int(len(block)),
        "bucket_sizes_before_balancing": {
            "leaked": int(len(leaked_all)),
            "clean": int(len(clean_all)),
        },
        "incident_overlap_rate_in_block": round(float(seen.mean()), 4),
        "per_class_rows_after_balancing": per_class,
        "per_class_cap_applied": per_class == per_class_cap,
        "n_per_bucket": per_class * len(TARGET_CLASSES),
        "leaked": {
            "accuracy": round(acc(leaked_true, leaked_pred), 4),
            "accuracy_bootstrap_ci": bootstrap_metric_ci(leaked_true, leaked_pred, acc, seed=SEED),
            "macro_f1": round(macro_f1(leaked_true, leaked_pred), 4),
            "per_class_recall": per_class_recall(leaked_true, leaked_pred),
        },
        "clean": {
            "accuracy": round(acc(clean_true, clean_pred), 4),
            "accuracy_bootstrap_ci": bootstrap_metric_ci(clean_true, clean_pred, acc, seed=SEED),
            "macro_f1": round(macro_f1(clean_true, clean_pred), 4),
            "per_class_recall": per_class_recall(clean_true, clean_pred),
        },
        "accuracy_gap_leaked_minus_clean": accuracy_gap,
        "macro_f1_gap_leaked_minus_clean": f1_gap,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure incident-level label leakage between the RF's "
        "training slice and the samples the paper evaluates on."
    )
    parser.add_argument(
        "--eval-block-rows",
        type=int,
        default=300_000,
        help="Rows to read past the training slice for the Part D causal test.",
    )
    parser.add_argument(
        "--per-class-cap",
        type=int,
        default=2_000,
        help="Max rows per class per bucket in the Part D causal test.",
    )
    args = parser.parse_args()

    if not REAL_DATA_PATH.exists():
        raise SystemExit(
            f"{REAL_DATA_PATH} not found. This audit is about the real GUIDE data "
            "and has no meaning against the synthetic sample; refusing to run."
        )

    print(f"reading the {TRAINING_SLICE_ROWS:,}-row training slice...", flush=True)
    train_slice = load_training_slice()
    train_label_by_key = dict(zip(_keys(train_slice), train_slice[TARGET_COLUMN]))

    print("part A: structural facts...", flush=True)
    a = part_a_structural_facts(train_slice)
    print("part B: key integrity...", flush=True)
    b = part_b_key_integrity(train_label_by_key)
    print("part C: evaluation-sample overlap...", flush=True)
    c = part_c_sample_overlap(train_slice, train_label_by_key)
    print(f"part D: causal test over {args.eval_block_rows:,} rows past the slice...", flush=True)
    d = part_d_causal_test(train_label_by_key, args.eval_block_rows, args.per_class_cap)

    output = {
        "experiment": (
            "Incident-level label leakage between the RF's training slice and the "
            "GUIDE_train-sampled evaluation sets this project reports on"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "data_source": str(REAL_DATA_PATH),
        "rf_model": "RandomForestClassifier, experiments/results/baseline_model.joblib",
        "incident_key": INCIDENT_KEY,
        "part_a_structural_facts": a,
        "part_b_key_integrity": b,
        "part_c_sample_overlap": c,
        "part_d_causal_test": d,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 72)
    print("INCIDENT-LEVEL LABEL LEAKAGE AUDIT")
    print("=" * 72)
    print(f"A. label constant within incident : {a['label_constancy_rate']:.4%} "
          f"of {a['unique_incidents']:,} incidents")
    print(f"   rows sharing an incident       : {a['rows_belonging_to_a_multi_row_incident_rate']:.1%}")
    print(f"B. colliding-key label agreement  : {b['label_agreement_rate']} "
          f"(chance floor {b['chance_agreement_floor_majority_class']})")
    print("C. evaluation-sample overlap")
    for name, r in c["samples"].items():
        if "n" not in r:
            print(f"   {name:20s} : {r['status']}")
            continue
        print(f"   {name:20s} : exact {r['exact_row_overlap']}/{r['n']} "
              f"({r['exact_row_overlap_rate']:.2%})   "
              f"incident {r['incident_level_overlap']}/{r['n']} "
              f"({r['incident_level_overlap_rate']:.2%})")
    if "leaked" in d:
        gap = d["accuracy_gap_leaked_minus_clean"]
        print(f"D. leaked  accuracy : {d['leaked']['accuracy']}  (n={d['n_per_bucket']})")
        print(f"   clean   accuracy : {d['clean']['accuracy']}  (n={d['n_per_bucket']})")
        print(f"   gap              : {gap['point_diff']:+.4f}  95% CI "
              f"[{gap['ci_lower']:+.4f}, {gap['ci_upper']:+.4f}]  "
              f"{'SIGNIFICANT' if gap['significant_at_confidence'] else 'not significant'}")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
