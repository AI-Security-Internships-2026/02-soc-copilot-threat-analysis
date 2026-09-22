#!/usr/bin/env python3
"""One-click reproduction of the M3 guardrail benchmark (issue #37, M3.3 Part B).

Dispatches to the detector-scoring logic in experiments/m3_2_learned_detectors.py
and experiments/m3_2_heuristic_detectors.py via their `run()` entry points --
this script has no scoring logic of its own, so there is exactly one copy of
each detector's implementation.

usage (from repo root):
    python scripts/benchmark_soc_injection.py --detector all
    python scripts/benchmark_soc_injection.py --detector l2 --daily-call-budget 300
    python scripts/benchmark_soc_injection.py --detector l3 --daily-call-budget 300
    python scripts/benchmark_soc_injection.py --reproduce_only_checksum
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from experiments import m3_2_learned_detectors as learned
from experiments import m3_2_heuristic_detectors as heuristic
from experiments import m3_2_build_detector_matrix as matrix

LEARNED_DETECTORS = {"l1", "l2", "l3"}
HEURISTIC_DETECTORS = {"h1", "h2", "h3", "h_union"}
ALL_DETECTORS = LEARNED_DETECTORS | HEURISTIC_DETECTORS

CHECKSUM_TARGETS = [
    learned.OUTPUT_PATH,
    heuristic.OUTPUT_PATH,
    Path("docs/m3-2-detector-family-matrix.md"),
    Path("experiments/results/m3_2_familywise_failure_analysis.json"),
]


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def reproduce_only_checksum() -> None:
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {str(p): _sha256(p) for p in CHECKSUM_TARGETS},
    }
    print(json.dumps(manifest, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--detector",
        choices=sorted(ALL_DETECTORS | {"all"}),
        default="all",
    )
    parser.add_argument("--daily-call-budget", type=int, default=None, help="cap live Groq calls for L2/L3 this invocation")
    parser.add_argument("--reproduce_only_checksum", action="store_true", help="print SHA-256 of existing outputs, no re-scoring")
    parser.add_argument("--skip-matrix", action="store_true", help="skip rebuilding the Part C failure matrix after scoring")
    args = parser.parse_args()

    if args.reproduce_only_checksum:
        reproduce_only_checksum()
        return

    detectors = sorted(ALL_DETECTORS) if args.detector == "all" else [args.detector]
    learned_to_run = [d for d in detectors if d in LEARNED_DETECTORS]
    heuristic_to_run = [d for d in detectors if d in HEURISTIC_DETECTORS]

    if learned_to_run:
        learned.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = json.loads(learned.OUTPUT_PATH.read_text()) if learned.OUTPUT_PATH.exists() else {}
        for key in learned_to_run:
            print(f"running {key}...")
            output[key] = learned.run(key, daily_call_budget=args.daily_call_budget)
        output["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        output["git_sha"] = learned.git_sha()
        learned.OUTPUT_PATH.write_text(json.dumps(output, indent=2))
        print(f"saved {learned.OUTPUT_PATH}")

    if heuristic_to_run:
        heuristic.OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = json.loads(heuristic.OUTPUT_PATH.read_text()) if heuristic.OUTPUT_PATH.exists() else {}
        if "all" in [args.detector]:
            output.update(heuristic.run("all"))
        else:
            for key in heuristic_to_run:
                output[key] = heuristic.run(key)
        output["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        output["git_sha"] = heuristic.git_sha()
        heuristic.OUTPUT_PATH.write_text(json.dumps(output, indent=2))
        print(f"saved {heuristic.OUTPUT_PATH}")

    if not args.skip_matrix and learned.OUTPUT_PATH.exists() and heuristic.OUTPUT_PATH.exists():
        matrix.main()


if __name__ == "__main__":
    main()
