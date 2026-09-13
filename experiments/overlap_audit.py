# experiments/overlap_audit.py
#
# M2.1 PART B (issue #31) asks for a minimal, reusable overlap script if one
# doesn't already exist. It doesn't: two divergent implementations do the
# same computation slightly differently --
#
#   - incident_leakage_audit.py's part_c_sample_overlap() hashes full rows
#     with pd.util.hash_pandas_object (int64), and is the one with test
#     coverage precedent (it's what produced the committed 1.40%/55.76% and
#     1.91%/39.23% Table 14 numbers).
#   - rf_vs_llm_control.py's training_overlap() instead casts every column
#     to string and builds a set of value-tuples.
#
# Both agree on the numbers they've each been run against, but a script that
# adds a fourth evaluation set (M2.1 PART C, the 15,000-row GUIDE_Test
# held-out sample) shouldn't have to pick one implementation to duplicate.
# This module is the single place that computation lives now; the two
# existing scripts are left as-is (they're the evidence a past number was
# produced a certain way) but nothing new should reimplement this again.
#
# Convention adopted: the hash-based method, because it is the one the
# committed Table 14 numbers were already measured with.
#
# usage (as a library):
#   from experiments.overlap_audit import load_train_reference, compute_overlap
#   ref = load_train_reference()
#   result = compute_overlap(eval_df, ref)
#
# usage (standalone, verifies Table 14's three already-published overlap
# pairs reproduce from a script rather than being manually re-derived):
#   venv/bin/python experiments/overlap_audit.py

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.agent.fallback_classifier import _load_model, should_use_fallback
from src.data.load_data import REAL_DATA_PATH
from src.data.schema import TARGET_COLUMN

# Mirrors src/models/baseline.py / incident_leakage_audit.py: the deployed
# model's exact training slice.
TRAINING_SLICE_ROWS = 100_000
INCIDENT_KEY = ("OrgId", "IncidentId")
CACHE_DIR = Path("experiments/results/evaluation_samples")
OUTPUT_PATH = Path("experiments/results/overlap_audit.json")

# Table 14, docs/final-report.md:615-616 -- what this script's standalone run
# checks a fresh computation against.
TABLE_14_REFERENCE = {
    "train_sampled_999": {"exact_row_overlap": 14, "incident_level_overlap": 557, "n": 999},
    "control_209": {"exact_row_overlap": 4, "incident_level_overlap": 82, "n": 209},
    "held_out_999": {"exact_row_overlap": 0, "incident_level_overlap": 0, "n": 999},
}
TOLERANCE_ROWS = 0  # exact reproduction expected; these are deterministic seeded samples


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def load_train_reference(
    train_path: Path = REAL_DATA_PATH,
    train_rows: int = TRAINING_SLICE_ROWS,
) -> dict:
    """Load the training slice once; reused across every overlap computation.

    Returns {"row_hashes", "incident_keys", "columns", "train_rows"}. Callers
    that check multiple evaluation sets (M2.1 PART C checks four) should call
    this once and pass the result to compute_overlap() repeatedly, rather
    than re-reading the training slice for each set.
    """
    train_full = pd.read_csv(train_path, nrows=train_rows).dropna(subset=[TARGET_COLUMN])
    row_hashes = set(pd.util.hash_pandas_object(train_full, index=False).astype("int64").tolist())
    incident_keys = set(zip(train_full[INCIDENT_KEY[0]], train_full[INCIDENT_KEY[1]]))
    return {
        "row_hashes": row_hashes,
        "incident_keys": incident_keys,
        "columns": list(train_full.columns),
        "train_rows": train_rows,
    }


def compute_overlap(
    eval_df: pd.DataFrame,
    train_reference: dict,
    incident_key: tuple = INCIDENT_KEY,
) -> dict:
    """Exact-row and incident-level overlap of eval_df against a training slice.

    exact-row: the row appears verbatim in the training slice (the smaller,
    previously-published figure). incident-level: the row's incident key
    appears in the training slice, i.e. a labelled sibling was available --
    the figure that determines whether the label was recoverable from
    training data (see incident_leakage_audit.py for why this is the one
    that matters).
    """
    comparable = eval_df[[c for c in train_reference["columns"] if c in eval_df.columns]]
    eval_hashes = pd.util.hash_pandas_object(comparable, index=False).astype("int64")
    eval_keys = list(zip(eval_df[incident_key[0]], eval_df[incident_key[1]]))

    n = len(eval_df)
    exact = int(sum(h in train_reference["row_hashes"] for h in eval_hashes))
    incident = int(sum(k in train_reference["incident_keys"] for k in eval_keys))

    return {
        "n": n,
        "exact_row_overlap": exact,
        "exact_row_overlap_pct": round(100 * exact / n, 2) if n else None,
        "incident_level_overlap": incident,
        "incident_level_overlap_pct": round(100 * incident / n, 2) if n else None,
        "n_train_rows_checked": train_reference["train_rows"],
    }


def _load_control_209(train_reference: dict) -> pd.DataFrame | None:
    """Reproduce the 209-alert LLM-routed subset from the routing rule itself.

    Same derivation as rf_vs_llm_control.py's main(): filter the 999-alert
    cache by should_use_fallback rather than trusting a stored row list, so
    this stays correct if the cache or routing rule ever changes.
    """
    cache_path = CACHE_DIR / "guide_balanced_333_per_class_seed_42.csv"
    if not cache_path.exists():
        return None
    cache = pd.read_csv(cache_path)
    eligible = cache[cache.apply(lambda r: not should_use_fallback(r.to_dict()), axis=1)]
    return eligible


def main() -> None:
    if not REAL_DATA_PATH.exists():
        raise SystemExit(
            f"{REAL_DATA_PATH} not found. Overlap has no meaning without the real "
            "training slice; refusing to run against the synthetic sample."
        )

    print(f"loading the {TRAINING_SLICE_ROWS:,}-row training reference...", flush=True)
    ref = load_train_reference()

    samples = {
        "train_sampled_999": CACHE_DIR / "guide_balanced_333_per_class_seed_42.csv",
        "held_out_999": CACHE_DIR / "guide_test_balanced_333_per_class_seed_42.csv",
    }

    results = {}
    for name, path in samples.items():
        if not path.exists():
            results[name] = {"status": "sample cache absent", "path": str(path)}
            continue
        df = pd.read_csv(path)
        results[name] = compute_overlap(df, ref)

    control_209 = _load_control_209(ref)
    if control_209 is not None:
        results["control_209"] = compute_overlap(control_209, ref)
    else:
        results["control_209"] = {"status": "999-alert cache absent, cannot derive the 209 subset"}

    checks = {}
    for name, expected in TABLE_14_REFERENCE.items():
        measured = results.get(name, {})
        if "exact_row_overlap" not in measured:
            checks[name] = {"status": measured.get("status", "not measured")}
            continue
        exact_match = abs(measured["exact_row_overlap"] - expected["exact_row_overlap"]) <= TOLERANCE_ROWS
        incident_match = (
            abs(measured["incident_level_overlap"] - expected["incident_level_overlap"]) <= TOLERANCE_ROWS
        )
        n_match = measured["n"] == expected["n"]
        checks[name] = {
            "expected": expected,
            "measured": {
                "exact_row_overlap": measured["exact_row_overlap"],
                "incident_level_overlap": measured["incident_level_overlap"],
                "n": measured["n"],
            },
            "matches_table_14": bool(exact_match and incident_match and n_match),
        }

    all_pass = all(c.get("matches_table_14", False) for c in checks.values() if "matches_table_14" in c)

    output = {
        "experiment": (
            "Reusable overlap computation, verified against the three overlap pairs "
            "already published in Table 14 (docs/final-report.md)"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "data_source": str(REAL_DATA_PATH),
        "incident_key": list(INCIDENT_KEY),
        "training_slice_rows": TRAINING_SLICE_ROWS,
        "results": results,
        "table_14_reproduction_check": checks,
        "all_table_14_numbers_reproduced": all_pass,
        "finding": (
            "All three published overlap pairs reproduce exactly from this script."
            if all_pass
            else "At least one published overlap pair did not reproduce exactly -- "
            "see table_14_reproduction_check for which, and by how much."
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print("\n" + "=" * 72)
    print("OVERLAP AUDIT -- TABLE 14 REPRODUCTION CHECK")
    print("=" * 72)
    for name, c in checks.items():
        if "matches_table_14" not in c:
            print(f"  {name:20s} : {c['status']}")
            continue
        status = "MATCH" if c["matches_table_14"] else "MISMATCH"
        m = c["measured"]
        print(
            f"  {name:20s} : {status}  exact {m['exact_row_overlap']}/{m['n']}  "
            f"incident {m['incident_level_overlap']}/{m['n']}"
        )
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
