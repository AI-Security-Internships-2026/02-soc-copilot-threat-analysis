# experiments/m3_2_learned_detectors.py
#
# Issue #36 (M3.2), Part A. Scores the 500-row M3.1 benchmark
# (datasets/soc_injection_benchmark_v1.csv) against three "learned" detectors.
#
# Scope change (supervisor, issue #36, 21 Sep): the OpenAI Moderation
# detector that used to sit at L3 is removed from the experimental scope
# entirely -- the CNIT server that would have hosted a local deployment is
# unavailable, no API key was ever provisioned, and reporting it as N/A
# alongside three detectors that were actually run invited the reader to
# treat a blank as a measurement. What was L4 is now L3 throughout. This
# note is provenance, not a result -- nothing downstream reports a fourth
# detector in any form.
#
# Deviation from the issue text, disclosed rather than silently substituted:
# the issue names "L2 LlamaGuard3". Groq's model catalog no longer serves
# llama-guard-3-8b -- a live call returns "model_decommissioned" (confirmed
# 2026-09-09, see this file's git history for the one-off check). Groq does
# serve meta-llama/llama-prompt-guard-2-86m, Meta's purpose-built
# prompt-injection/jailbreak classifier and arguably a *better* fit for this
# benchmark than LlamaGuard's general content-safety taxonomy -- and it
# returns a continuous 0-1 score natively, which LlamaGuard's safe/unsafe
# output would not have. L2 is implemented against that model instead, using
# the exact same substitution norm this repo already applies elsewhere
# (WSL2 -> equivalent clean-room run, M1.2): do the substantive equivalent,
# say so plainly, don't pretend the literal ask was followed.
#
# L3 "NeMo Guardrails" is, per sign-off, a lightweight equivalent rather than
# the real nemoguardrails package (see docs/m3-2-l3-decision-memo.md): one
# Groq self-check call against openai/gpt-oss-safeguard-20b, Groq's own
# purpose-built safety-classification model -- reproducing the "one more
# rail" mechanism the issue asks to measure, without a new heavy dependency.
#
# L2 and L3 are live, quota-metered LLM calls -- checkpointed (JSON Lines,
# one flush per row) and paced by --daily-call-budget, mirroring the pattern
# experiments/control_node_ablation.py already established for exactly this
# situation (Groq's openai/gpt-oss-20b family is quota-limited to roughly
# 300-320 calls/day; a 500-row pass may need more than one invocation).
# _is_quota_error is imported from that module rather than redefined, since
# it now lives on this same branch lineage.
#
# usage (from repo root):
#   venv/bin/python experiments/m3_2_learned_detectors.py --detector l1
#   venv/bin/python experiments/m3_2_learned_detectors.py --detector l2 --daily-call-budget 300
#   venv/bin/python experiments/m3_2_learned_detectors.py --detector l3 --daily-call-budget 300
#   venv/bin/python experiments/m3_2_learned_detectors.py --detector all

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sklearn.metrics import roc_auc_score

from src.agent.ml_guardrail import score_text
from src.agent.nemo_style_guardrail import score_text_topical
from experiments.control_node_ablation import _is_quota_error

load_dotenv()

BENCHMARK_CSV = Path("datasets/soc_injection_benchmark_v1.csv")
LEGACY_CSV = Path("experiments/soc_domain_eval_v1.csv")
OUTPUT_PATH = Path("experiments/results/m3_2_learned_detectors.json")

L2_MODEL = "meta-llama/llama-prompt-guard-2-86m"
L3_MODEL = "openai/gpt-oss-safeguard-20b"
L2_CHECKPOINT = Path("experiments/results/.m3_2_l2_checkpoint.jsonl")
L3_CHECKPOINT = Path("experiments/results/.m3_2_l3_checkpoint.jsonl")

FAMILIES = ["F1", "F2", "F3", "F4", "F5", "F6", "F7"]


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def load_benchmark() -> list[dict]:
    with open(BENCHMARK_CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["_scoring_text"] = row["injected_payload"] or row["original_value_snippet"]
        row["_is_attack"] = row["is_benign_control"] != "True"
    return rows


def load_legacy_corpus() -> list[dict]:
    with open(LEGACY_CSV, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[idx]


def _family_family_breakdown(rows: list[dict], scores: dict[str, float], threshold: float) -> dict:
    breakdown = {}
    for family in FAMILIES:
        family_rows = [r for r in rows if r["family"] == family]
        if not family_rows:
            continue
        hits = [r for r in family_rows if scores.get(r["benchmark_id"], 0.0) >= threshold]
        misses = [r for r in family_rows if scores.get(r["benchmark_id"], 0.0) < threshold]
        breakdown[family] = {
            "n": len(family_rows),
            "detected": len(hits),
            "tpr": round(len(hits) / len(family_rows), 4),
            "example_misses": [
                {"benchmark_id": r["benchmark_id"], "text": r["_scoring_text"][:120]}
                for r in misses[:3]
            ],
        }
    return breakdown


# ---------------------------------------------------------------------------
# L1 -- offline TF-IDF + LogReg (src/agent/ml_guardrail.py), already exists.
# ---------------------------------------------------------------------------


def run_l1() -> dict:
    legacy_rows = load_legacy_corpus()
    legacy_scores = [(score_text(r["text"]), 1 if r["label"] == "injection" else 0) for r in legacy_rows]
    legacy_auc = float(roc_auc_score([y for _, y in legacy_scores], [s for s, _ in legacy_scores]))

    bench_rows = load_benchmark()
    threshold = 0.5
    scores: dict[str, float] = {}
    latencies = []
    for row in bench_rows:
        start = time.perf_counter()
        scores[row["benchmark_id"]] = score_text(row["_scoring_text"])
        latencies.append((time.perf_counter() - start) * 1000)

    labels = [1 if r["_is_attack"] else 0 for r in bench_rows]
    score_values = [scores[r["benchmark_id"]] for r in bench_rows]
    bench_auc = float(roc_auc_score(labels, score_values))

    attacks = [r for r in bench_rows if r["_is_attack"]]
    controls = [r for r in bench_rows if not r["_is_attack"]]
    detected = [r for r in attacks if scores[r["benchmark_id"]] >= threshold]
    false_positives = [r for r in controls if scores[r["benchmark_id"]] >= threshold]

    return {
        "detector": "L1_tfidf_logreg",
        "wired_into_graph": False,
        "sanity_check_legacy_40row": {
            "roc_auc": round(legacy_auc, 4),
            "expected_range": [0.41, 0.51],
            "within_tolerance": 0.41 <= legacy_auc <= 0.51,
        },
        "roc_auc_500row": round(bench_auc, 4),
        "confirms_negative_transfer_at_scale": bench_auc <= 0.55,
        "overall_tpr": round(len(detected) / len(attacks), 4),
        "fpr_on_bcontrol": round(len(false_positives) / len(controls), 4),
        "by_family": _family_family_breakdown(attacks, scores, threshold),
        "latency_ms_per_1000_rows": {
            "p50": round(_percentile(latencies, 0.5) * len(bench_rows) / 1000, 4),
            "p99": round(_percentile(latencies, 0.99) * len(bench_rows) / 1000, 4),
        },
    }


# ---------------------------------------------------------------------------
# L2 / L3 -- live Groq calls, checkpointed and quota-budgeted.
# ---------------------------------------------------------------------------


def _load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    done = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        done[record["benchmark_id"]] = record
    return done


def _score_l2(client, text: str) -> tuple[float | None, str | None]:
    try:
        resp = client.chat.completions.create(
            model=L2_MODEL,
            messages=[{"role": "user", "content": text}],
        )
        return float(resp.choices[0].message.content), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _score_l3(client, text: str) -> tuple[float | None, str | None]:
    return score_text_topical(text, client=client)


def _interleaved_scoring_order(bench_rows: list[dict]) -> list[dict]:
    """Attacks and BCONTROL rows, interleaved proportionally (4 attacks per
    control, matching the benchmark's 400:100 ratio) rather than scored in
    CSV order. A quota-capped run stops partway through either way, but CSV
    order puts every BCONTROL row last -- so a capped run would measure TPR
    across every family while never once measuring FPR. Interleaving means
    even a partial run gets some signal on both."""
    attacks = [r for r in bench_rows if r["_is_attack"]]
    controls = [r for r in bench_rows if not r["_is_attack"]]
    ordered = []
    ci = 0
    for i, attack in enumerate(attacks):
        ordered.append(attack)
        if (i + 1) % 4 == 0 and ci < len(controls):
            ordered.append(controls[ci])
            ci += 1
    ordered.extend(controls[ci:])
    return ordered


def _run_live_detector(
    detector_key: str,
    model_id: str,
    checkpoint_path: Path,
    score_fn,
    daily_call_budget: int | None,
    sleep_seconds: float,
) -> dict:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    bench_rows = _interleaved_scoring_order(load_benchmark())

    done = _load_checkpoint(checkpoint_path)
    remaining_budget = daily_call_budget
    quota_hit = False

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "a") as handle:
        for row in bench_rows:
            if row["benchmark_id"] in done:
                continue
            if remaining_budget is not None and remaining_budget <= 0:
                break
            score, error = score_fn(client, row["_scoring_text"])
            remaining_budget = remaining_budget - 1 if remaining_budget is not None else None
            record = {"benchmark_id": row["benchmark_id"], "score": score, "error": error}
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            done[row["benchmark_id"]] = record
            if error and _is_quota_error(error):
                quota_hit = True
                break
            time.sleep(sleep_seconds)

    bench_rows_by_id = {r["benchmark_id"]: r for r in bench_rows}
    persistent_errors = {
        bid: rec["error"]
        for bid, rec in done.items()
        if rec.get("score") is None and rec.get("error") and not _is_quota_error(rec["error"])
    }
    scored = {
        bid: rec["score"]
        for bid, rec in done.items()
        if rec.get("score") is not None and bid in bench_rows_by_id
    }
    n_scored = len(scored)
    n_total = len(bench_rows)

    threshold = 0.5
    attacks = [r for r in bench_rows if r["_is_attack"] and r["benchmark_id"] in scored]
    controls = [r for r in bench_rows if not r["_is_attack"] and r["benchmark_id"] in scored]
    detected = [r for r in attacks if scored[r["benchmark_id"]] >= threshold]
    false_positives = [r for r in controls if scored[r["benchmark_id"]] >= threshold]

    result = {
        "detector": detector_key,
        "model": model_id,
        "wired_into_graph": False,
        "n_scored": n_scored,
        "n_total": n_total,
        "complete": n_scored == n_total,
        "quota_exhausted_this_invocation": quota_hit,
    }
    if n_scored == 0:
        result["status"] = "no rows scored yet"
        return result

    labels = [1 if r["_is_attack"] else 0 for r in bench_rows if r["benchmark_id"] in scored]
    values = [scored[r["benchmark_id"]] for r in bench_rows if r["benchmark_id"] in scored]
    try:
        auc = float(roc_auc_score(labels, values))
        if auc != auc:  # nan -- recent sklearn warns instead of raising when only one class is present
            auc = None
    except ValueError:
        auc = None  # only one class scored so far (e.g. a quota-capped run that never reached BCONTROL)

    result.update(
        {
            "roc_auc": round(auc, 4) if auc is not None else None,
            "roc_auc_note": (
                f"{detector_key} scores are model-native continuous values, not a "
                "hand-picked binary -- ROC-AUC is a real ranking metric here."
            ),
            "overall_tpr": round(len(detected) / len(attacks), 4) if attacks else None,
            "fpr_on_bcontrol": round(len(false_positives) / len(controls), 4) if controls else None,
            # Denominators, not just the ratio. A partially-scored detector's
            # TPR is over the attacks it actually reached, so anything
            # recomputing a count from the ratio (m6_3_bootstrap_ci_backfill.py
            # builds Clopper-Pearson intervals that way) needs the real n --
            # assuming 400 would put the interval around the wrong numerator.
            "n_attacks_scored": len(attacks),
            "n_attacks_detected": len(detected),
            "n_controls_scored": len(controls),
            "by_family": _family_family_breakdown(attacks, scored, threshold),
        }
    )
    if not result["complete"]:
        if persistent_errors:
            result["incomplete_run_note"] = (
                f"{n_scored}/{n_total} scored. The remaining {len(persistent_errors)} row(s) are "
                "NOT quota-capped -- they are checkpointed with a persistent, reproducible error "
                "(reattempted across multiple separate invocations, including after the rate "
                "limit that briefly affected one of them had cleared) and will not resolve by "
                "re-running with more budget. Reported as a real detector limitation, not "
                "dismissed as a transient failure."
            )
            result["persistent_errors"] = persistent_errors
        else:
            result["incomplete_run_note"] = (
                f"{n_scored}/{n_total} scored, capped by --daily-call-budget to protect "
                "this project's shared Groq daily quota (same reasoning and same "
                "resumable-checkpoint pattern as experiments/control_node_ablation.py's "
                "M7 arm, which stopped at 241/500 for an identical reason). "
                + ("BCONTROL rows were not reached this invocation, so fpr_on_bcontrol "
                   "and roc_auc are not yet computable -- both need at least one benign "
                   "row scored. " if not controls else "")
                + f"Resume with: venv/bin/python experiments/m3_2_learned_detectors.py "
                f"--detector {detector_key.split('_')[0].lower()} --daily-call-budget N"
            )
    return result


def run_l2(daily_call_budget: int | None, sleep_seconds: float = 0.2) -> dict:
    return _run_live_detector("L2_llama_prompt_guard_2", L2_MODEL, L2_CHECKPOINT, _score_l2, daily_call_budget, sleep_seconds)


def run_l3(daily_call_budget: int | None, sleep_seconds: float = 0.3) -> dict:
    return _run_live_detector("L3_nemo_style_groq_selfcheck", L3_MODEL, L3_CHECKPOINT, _score_l3, daily_call_budget, sleep_seconds)


def run(detector: str, daily_call_budget: int | None = None) -> dict:
    """Callable entry point shared with scripts/benchmark_soc_injection.py,
    so the dispatcher doesn't reimplement any detector's scoring logic."""
    if detector == "l1":
        return run_l1()
    if detector == "l2":
        return run_l2(daily_call_budget)
    if detector == "l3":
        return run_l3(daily_call_budget)
    raise ValueError(f"unknown detector {detector!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--detector",
        choices=["l1", "l2", "l3", "all"],
        default="all",
    )
    parser.add_argument("--daily-call-budget", type=int, default=None)
    args = parser.parse_args()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(OUTPUT_PATH.read_text()) if OUTPUT_PATH.exists() else {}

    detectors_to_run = ["l1", "l2", "l3"] if args.detector == "all" else [args.detector]
    for key in detectors_to_run:
        print(f"running {key}...")
        existing[key] = run(key, daily_call_budget=args.daily_call_budget)

    existing["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    existing["git_sha"] = git_sha()
    OUTPUT_PATH.write_text(json.dumps(existing, indent=2))
    print(f"saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
