# experiments/control_node_ablation.py
#
# Ablation study on the RF/LLM control-node architecture, and the concrete
# answer to "what happens on incomplete alert context" -- both were raised
# together at the same review because they are the same question asked two
# ways: which node decides, and how does that decision hold up as evidence
# gets sparser.
#
# Four arms, all scored on the identical 999-alert balanced cache so the
# comparison is paired the same way rf_vs_llm_control.py's is:
#
#   (a) rf_primary,  explanation ON   -- current production graph
#   (b) rf_primary,  explanation OFF  -- SOC_COPILOT_SKIP_EXPLANATION=1
#   (c) legacy_hybrid                 -- Weeks 6-14 evidence-routed graph
#   (d) llm_primary                   -- LLM decides every alert, unconditionally
#
# Arms (a), (c), (d) make live Groq calls. The original design ran all three
# at the full 999-alert scale (~2,207 calls, signed off 2026-09-01), but that
# turned out to need ~1.3-2.2M tokens against Groq's openai/gpt-oss-20b daily
# quota of 200,000 -- roughly 300-320 calls/day at this pipeline's actual
# per-call cost, discovered only after the quota was hit mid-run. --reduced
# scores a stratified ~299-alert subsample instead (see REDUCED_BIN_TARGETS),
# sized to fit a realistic 1-2 day quota budget while keeping every evidence
# bin represented. Arm (b) is fully offline and doubles as a proof: since
# explain_with_llm structurally cannot write predicted_label/confidence
# (src/agent/nodes.py), arm (a) and arm (b) must produce IDENTICAL verdicts
# row-for-row on whichever sample is used. This script asserts that rather
# than assuming it -- a mismatch would mean the architectural claim is false,
# which is a finding, not a bug to silently paper over.
#
# Every alert is also tagged with its evidence_field_count (0-3), so each
# arm's accuracy/recall/F1 can be broken out by context density. Bin 3 has
# only 29 rows even in the full 999-alert cache and is reported with an
# explicit low-support caveat rather than as a reliable per-class number.
#
# Resumable: each arm checkpoints completed rows to
# experiments/results/.control_node_ablation_checkpoints/arm_<key>.jsonl as
# it goes, so a killed/interrupted run (e.g. a quota exhaustion mid-arm)
# picks up where it left off on the next invocation instead of re-spending
# already-consumed API calls.
#
# usage (from repo root):
#   venv/bin/python experiments/control_node_ablation.py --reduced         # realistic quota budget
#   venv/bin/python experiments/control_node_ablation.py                   # full 999 (needs ~6-11 days of quota)
#   venv/bin/python experiments/control_node_ablation.py --skip-live       # arm (b) only, full 999, offline
#   venv/bin/python experiments/control_node_ablation.py --reduced --arms a b     # subset

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score

from src.agent.fallback_classifier import evidence_field_count
from src.agent.graph import build_triage_graph
from experiments.rf_vs_llm_control import calibration_table

CACHE_PATH = Path(
    "experiments/results/evaluation_samples/guide_balanced_333_per_class_seed_42.csv"
)
OUTPUT_PATH = Path("experiments/results/control_node_ablation.json")
CHECKPOINT_DIR = Path("experiments/results/.control_node_ablation_checkpoints")
EVIDENCE_BINS = (0, 1, 2, 3)
LOW_SUPPORT_BIN = 3
LOW_SUPPORT_CAVEAT = (
    "n=29 in the full 999-alert sample -- per-class recall/precision at this "
    "support is not reliable and should not be read as a stable estimate."
)

ARM_CONFIG = {
    "a": {"mode": "rf_primary", "skip_explanation": False, "label": "rf_primary, explanation on"},
    "b": {"mode": "rf_primary", "skip_explanation": True, "label": "rf_primary, explanation off"},
    "c": {"mode": "legacy_hybrid", "skip_explanation": False, "label": "legacy_hybrid (evidence-routed)"},
    "d": {"mode": "llm_primary", "skip_explanation": False, "label": "llm_primary (LLM decides every alert)"},
}

# 2026-09-01: the full-scale design (999 alerts x 3 live arms, ~2,200 calls)
# was signed off before discovering Groq's openai/gpt-oss-20b daily quota is
# 200,000 tokens -- roughly 300-320 explanation/decision calls at this
# pipeline's actual per-call token cost, not the ~2,200 the design needs.
# Waiting for the quota to refill would take an estimated 6-11 days (a
# rolling 24h window, not an instant daily reset), which is impractical.
# REDUCED_BIN_TARGETS keeps every bin represented -- bin 3 kept at its full
# 29 rows since it is already the thinnest population in the 999-alert
# cache, not because 29 is a good number on its own -- while cutting bins
# 0-2 to what a realistic 1-2 day quota budget can actually score across
# three live arms. This is a sample-size reduction, not a bin-selection
# choice: proportions are preserved as closely as a fixed floor allows.
REDUCED_BIN_TARGETS = {0: 126, 1: 94, 2: 50, 3: 29}  # sums to 299


def build_reduced_sample(cache: pd.DataFrame, bin_targets: dict[int, int], seed: int = 42) -> pd.DataFrame:
    """Deterministic stratified subsample of the 999-alert cache by evidence bin."""
    bins = cache.apply(lambda r: evidence_field_count(r.to_dict()), axis=1)
    parts = []
    for b, target_n in bin_targets.items():
        pool = cache[bins == b]
        n = min(target_n, len(pool))
        parts.append(pool.sample(n=n, random_state=seed))
    reduced = pd.concat(parts).sort_index()
    return reduced


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _checkpoint_path(arm_key: str) -> Path:
    return CHECKPOINT_DIR / f"arm_{arm_key}.jsonl"


def _load_checkpoint(arm_key: str) -> dict[int, dict[str, Any]]:
    """Rows already scored for this arm, keyed by row index -- lets a killed
    run resume instead of re-spending live API calls on rows already done.
    Appended incrementally as JSON Lines, one flushed write per row, so a
    hard kill loses at most the one row in flight."""
    path = _checkpoint_path(arm_key)
    if not path.exists():
        return {}
    done: dict[int, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        done[record["_row_index"]] = record
    return done


def run_arm(mode: str, sample: pd.DataFrame, skip_explanation: bool, arm_key: str, sleep_seconds: float = 0.3) -> list[dict[str, Any]]:
    """Run one graph mode over the full sample, returning a row per alert.

    Latency is timed inline (per-invoke wall time) rather than via a second
    pass through src/agent/benchmark.py's run_case() -- a second pass would
    re-invoke the graph and double the live API calls this run already costs.

    Resumable: rows already present in this arm's checkpoint file are
    skipped rather than re-run, so a killed process only loses the row it
    was mid-invoke on, not the whole arm.
    """
    if skip_explanation:
        os.environ["SOC_COPILOT_SKIP_EXPLANATION"] = "1"
    else:
        os.environ.pop("SOC_COPILOT_SKIP_EXPLANATION", None)

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = _checkpoint_path(arm_key)
    done = _load_checkpoint(arm_key)
    if done:
        print(f"    resuming from checkpoint: {len(done)}/{len(sample)} rows already done", flush=True)

    graph = build_triage_graph(mode=mode)
    rows: list[dict[str, Any]] = []
    total = len(sample)

    with open(checkpoint_path, "a") as checkpoint_file:
        for i, (row_index, row) in enumerate(sample.iterrows()):
            if int(row_index) in done:
                rows.append(done[int(row_index)])
                continue

            alert = row.to_dict()
            ground_truth = alert.pop("IncidentGrade")
            bin_count = evidence_field_count(alert)

            started = time.perf_counter()
            try:
                result = graph.invoke({"raw_alert": alert})
                elapsed = time.perf_counter() - started
                record = {
                    "_row_index": int(row_index),
                    "ground_truth": ground_truth,
                    "evidence_bin": bin_count,
                    "predicted_label": result.get("predicted_label"),
                    "confidence": result.get("confidence"),
                    "triage_path": result.get("triage_path"),
                    "rationale_status": result.get("rationale_status"),
                    "error": result.get("error"),
                    "latency_seconds": round(elapsed, 4),
                }
            except Exception as exc:
                elapsed = time.perf_counter() - started
                record = {
                    "_row_index": int(row_index),
                    "ground_truth": ground_truth,
                    "evidence_bin": bin_count,
                    "predicted_label": None,
                    "confidence": None,
                    "triage_path": "error",
                    "rationale_status": None,
                    "error": str(exc),
                    "latency_seconds": round(elapsed, 4),
                }
            rows.append(record)
            checkpoint_file.write(json.dumps(record) + "\n")
            checkpoint_file.flush()

            made_live_call = record["triage_path"] in ("llm", "llm_error") or record["rationale_status"] in (
                "generated",
                "unavailable",
            )
            if made_live_call and sleep_seconds:
                time.sleep(sleep_seconds)

            if (i + 1) % 100 == 0:
                print(f"    {i + 1}/{total}...", flush=True)

    return rows


def compute_arm_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("predicted_label") is not None]
    y_true = [r["ground_truth"] for r in scored]
    y_pred = [r["predicted_label"] for r in scored]

    overall = {
        "n_total": len(rows),
        "n_scored": len(scored),
        "n_unscored": len(rows) - len(scored),
        "accuracy": round(accuracy_score(y_true, y_pred), 4) if y_true else None,
        "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4) if y_true else None,
        "classification_report": classification_report(y_true, y_pred, zero_division=0, digits=3) if y_true else None,
    }

    by_bin: dict[str, Any] = {}
    for b in EVIDENCE_BINS:
        bin_rows = [r for r in scored if r["evidence_bin"] == b]
        if not bin_rows:
            by_bin[str(b)] = {"n": 0}
            continue
        bt = [r["ground_truth"] for r in bin_rows]
        bp = [r["predicted_label"] for r in bin_rows]
        entry = {
            "n": len(bin_rows),
            "accuracy": round(accuracy_score(bt, bp), 4),
            "macro_f1": round(f1_score(bt, bp, average="macro", zero_division=0), 4),
            "classification_report": classification_report(bt, bp, zero_division=0, digits=3),
        }
        if b == LOW_SUPPORT_BIN:
            entry["caveat"] = LOW_SUPPORT_CAVEAT
        by_bin[str(b)] = entry

    latencies = [r["latency_seconds"] for r in rows if r.get("latency_seconds") is not None]
    latency = {
        "mean_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else None,
        "total_wall_seconds": round(sum(latencies), 2) if latencies else None,
        "throughput_alerts_per_second": round(len(latencies) / sum(latencies), 4) if latencies and sum(latencies) else None,
    }

    return {"overall": overall, "by_evidence_bin": by_bin, "latency": latency}


def verify_explanation_cannot_change_verdict(rows_a: list[dict], rows_b: list[dict]) -> dict:
    """Arm (a) and arm (b) must agree on every verdict; assert it, don't assume it."""
    by_index_b = {r["_row_index"]: r for r in rows_b}
    mismatches = []
    for ra in rows_a:
        rb = by_index_b.get(ra["_row_index"])
        if rb is None:
            continue
        if ra.get("predicted_label") != rb.get("predicted_label") or ra.get("confidence") != rb.get("confidence"):
            mismatches.append(
                {
                    "_row_index": ra["_row_index"],
                    "arm_a_label": ra.get("predicted_label"),
                    "arm_a_confidence": ra.get("confidence"),
                    "arm_b_label": rb.get("predicted_label"),
                    "arm_b_confidence": rb.get("confidence"),
                }
            )
    if mismatches:
        raise RuntimeError(
            f"explanation changed the verdict/confidence on {len(mismatches)} alerts -- "
            "this contradicts the architectural claim that explain_with_llm cannot write "
            f"predicted_label/confidence. First mismatch: {mismatches[0]}"
        )
    return {"checked_n": len(rows_a), "mismatches": 0, "verdict": "explanation never changed a verdict, as designed"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablate the RF/LLM control-node architecture.")
    parser.add_argument("--arms", nargs="+", choices=list(ARM_CONFIG), default=list(ARM_CONFIG))
    parser.add_argument("--skip-live", action="store_true", help="run only arm (b), fully offline")
    parser.add_argument(
        "--reduced", action="store_true",
        help="stratified ~299-alert subsample for live arms, sized to fit a realistic Groq daily "
             "quota budget instead of the full 999 (see REDUCED_BIN_TARGETS)",
    )
    args = parser.parse_args()
    arms = ["b"] if args.skip_live else args.arms

    print(f"loading the 999-alert balanced evaluation cache...")
    full_sample = pd.read_csv(CACHE_PATH)

    sample_design = "reduced_299" if args.reduced else "full_999"
    if args.reduced:
        sample = build_reduced_sample(full_sample, REDUCED_BIN_TARGETS)
        print(f"  reduced mode: {len(sample)}-alert stratified subsample "
              f"(targets {REDUCED_BIN_TARGETS}); quota-driven, see script header")
    else:
        sample = full_sample

    results: dict[str, Any] = {}
    raw_rows: dict[str, list[dict]] = {}
    for arm in arms:
        config = ARM_CONFIG[arm]
        print(f"\n=== arm ({arm}): {config['label']} ===")
        rows = run_arm(config["mode"], sample, config["skip_explanation"], arm_key=arm)
        raw_rows[arm] = rows
        results[arm] = {"config": config, "metrics": compute_arm_metrics(rows)}
        acc = results[arm]["metrics"]["overall"]["accuracy"]
        print(f"  accuracy: {acc}")

    verification = None
    if "a" in raw_rows and "b" in raw_rows:
        print("\nverifying arm (a) and arm (b) produce identical verdicts...")
        verification = verify_explanation_cannot_change_verdict(raw_rows["a"], raw_rows["b"])
        print(f"  {verification['verdict']}")

    calibration = None
    if "d" in raw_rows:
        calibration = calibration_table(raw_rows["d"])
        print(f"\narm (d) calibration (LLM deciding every alert, including evidence-poor ones):")
        print(f"  gate inverted: {calibration['gate_behaviour']['gate_is_inverted']}")

    cross_arm_summary = {
        arm: {
            "label": results[arm]["config"]["label"],
            "accuracy": results[arm]["metrics"]["overall"]["accuracy"],
            "macro_f1": results[arm]["metrics"]["overall"]["macro_f1"],
            "by_evidence_bin_accuracy": {
                b: results[arm]["metrics"]["by_evidence_bin"].get(b, {}).get("accuracy")
                for b in ("0", "1", "2", "3")
            },
        }
        for arm in results
    }

    full_b_reference = None
    if args.reduced and OUTPUT_PATH.exists():
        # Preserve the full-999 offline arm-b run (already committed, free to
        # keep) as a top-line reference alongside the quota-limited reduced
        # arms, rather than losing it when this run's output overwrites the
        # file.
        try:
            previous = json.loads(OUTPUT_PATH.read_text())
            if previous.get("sample_design") in (None, "full_999") and "b" in previous.get("arms", {}):
                full_b_reference = previous["arms"]["b"]
        except (json.JSONDecodeError, KeyError):
            pass

    output = {
        "experiment": "Control-node ablation: which node decides, and what happens as evidence gets sparser",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "evaluation_sample": str(CACHE_PATH),
        "sample_design": sample_design,
        "sample_design_note": (
            "Reduced from the originally-planned full 999-alert design to a stratified ~299-alert "
            "subsample because Groq's openai/gpt-oss-20b daily token quota (200,000) supports "
            "roughly 300-320 live calls at this pipeline's actual per-call cost, not the ~2,200 the "
            "full design needs; see REDUCED_BIN_TARGETS in this script."
            if args.reduced else "Full 999-alert balanced cache, no reduction."
        ),
        "evidence_bin_distribution": {str(b): int((sample.apply(lambda r: evidence_field_count(r.to_dict()), axis=1) == b).sum()) for b in EVIDENCE_BINS},
        "arms": results,
        "arm_b_full_999_reference": full_b_reference,
        "arm_a_vs_arm_b_verification": verification,
        "arm_d_calibration": calibration,
        "cross_arm_summary": cross_arm_summary,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nsaved to {OUTPUT_PATH}")

    for arm in arms:
        _checkpoint_path(arm).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
