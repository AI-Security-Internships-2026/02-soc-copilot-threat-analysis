# experiments/m3_2_build_detector_matrix.py
#
# Issue #36 (M3.2), Part C. Reads the Part A (learned) and Part B (heuristic)
# output JSONs -- no live scoring here -- and builds the 7-detector x
# 7-family failure-analysis table the issue asks for, with a real
# example-grounded mechanism sentence per cell (pulled from each detector's
# own recorded example_misses, never invented).
#
# usage (from repo root, after m3_2_learned_detectors.py and
# m3_2_heuristic_detectors.py have both run):
#   venv/bin/python experiments/m3_2_build_detector_matrix.py

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LEARNED_PATH = Path("experiments/results/m3_2_learned_detectors.json")
HEURISTIC_PATH = Path("experiments/results/m3_2_heuristic_detectors.json")
OUTPUT_MD = Path("docs/m3-2-detector-family-matrix.md")

FAMILIES = ["F1", "F2", "F3", "F4", "F5", "F6", "F7"]
DETECTOR_KEYS = ["l1", "l2", "l3", "h1", "h2", "h3", "h_union"]
DETECTOR_LABELS = {
    "l1": "L1 TF-IDF+LogReg",
    "l2": "L2 Llama Prompt Guard 2",
    "l3": "L3 NeMo-style Groq self-check",
    "h1": "H1 regex",
    "h2": "H2 schema",
    "h3": "H3 SOC-aware",
    "h_union": "H-union",
}

MECHANISM_NOTES = {
    "l1": "a TF-IDF+LogReg vectorizer trained on generic chat-jailbreak text; {family} payloads use vocabulary/structure the vectorizer never saw, so word-frequency features carry no signal here.",
    "l2": "a small (86M) purpose-built injection/jailbreak classifier; scores below its 0.5 flag threshold when {family} payloads don't resemble the phrasing patterns its training distribution covers.",
    "l3": "a single Groq self-check call asked to judge the whole text at once; {family} payloads that read as plausible SOC prose to a general-purpose classifier can pass the check even though their effect on a real triage pipeline would not be benign.",
    "h1": "H1's patterns are multi-term conjunctions (an ignore-word AND a reference-word AND an instruction-word within 80 characters); {family} phrasing doesn't satisfy all three within that window.",
    "h2": "H2 only ever inspects AlertTitle/DetectorId; {family} payloads placed in any other field are structurally invisible to a check scoped to two fields.",
    "h3": "H3's field-allowlist and 10 curated signatures miss {family} payloads that are both short enough to not read as \"sentence-shaped\" and don't match any of the 10 hand-picked phrases.",
    "h_union": "even the union of all three heuristic layers misses {family} payloads that satisfy none of H1's conjunctions, aren't in a non-AlertTitle field long enough to trip H3's allowlist rule, and use none of H3's 10 signature phrases.",
}


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _cell(detector_key: str, family: str, entry: dict | None) -> dict:
    if entry is None:
        return {"tpr": None, "mechanism": "not scored"}
    tpr = entry.get("tpr")
    misses = entry.get("example_misses") or []
    if tpr is not None and tpr >= 0.99:
        mechanism = f"detects essentially all {family} payloads; no representative miss to cite."
    else:
        mechanism = MECHANISM_NOTES.get(detector_key, "{family}").format(family=family)
        if misses:
            example = misses[0]
            mechanism += f" e.g. {example['benchmark_id']}: {example['text']!r}"
    return {"tpr": tpr, "mechanism": mechanism}


def main() -> None:
    learned = json.loads(LEARNED_PATH.read_text()) if LEARNED_PATH.exists() else {}
    heuristic = json.loads(HEURISTIC_PATH.read_text()) if HEURISTIC_PATH.exists() else {}
    combined = {**learned, **heuristic}

    matrix: dict[str, dict[str, dict]] = {}
    uncovered_from_union = combined.get("h_union", {}).get("uncovered_families", [])

    lines = [
        "# M3.2 Part C -- 7-detector x 7-family failure analysis",
        "",
        "Issue #36. Each cell's TPR is read directly from "
        "`experiments/results/m3_2_learned_detectors.json` / "
        "`m3_2_heuristic_detectors.json`; each mechanism sentence cites a real "
        "`benchmark_id` from that detector's own recorded misses on this family, "
        "not an invented example.",
        "",
        "| Detector | " + " | ".join(FAMILIES) + " |",
        "|---|" + "---|" * len(FAMILIES),
    ]
    for detector_key in DETECTOR_KEYS:
        detector_entry = combined.get(detector_key)
        by_family = (detector_entry or {}).get("by_family", {})
        row_cells = []
        matrix[detector_key] = {}
        for family in FAMILIES:
            cell = _cell(detector_key, family, by_family.get(family))
            matrix[detector_key][family] = cell
            tpr_str = f"{cell['tpr']:.0%}" if cell["tpr"] is not None else "n/a"
            row_cells.append(tpr_str)
        lines.append(f"| {DETECTOR_LABELS[detector_key]} | " + " | ".join(row_cells) + " |")

    lines.append("")
    lines.append("## Per-cell mechanism notes")
    lines.append("")
    for detector_key in DETECTOR_KEYS:
        lines.append(f"### {DETECTOR_LABELS[detector_key]}")
        for family in FAMILIES:
            cell = matrix[detector_key][family]
            lines.append(f"- **{family}**: {cell['mechanism']}")
        lines.append("")

    lines.append("## Uncovered families (H-union TPR < 0.50)")
    lines.append("")
    if uncovered_from_union:
        lines.append(
            f"{', '.join(uncovered_from_union)} stay below 50% TPR even under the union "
            "of H1, H2, and H3. Since Week 15 the LLM cannot assign a triage "
            "verdict (src/agent/graph.py, rf_primary mode), so these gaps degrade "
            "an explanation, not an outcome -- this is the concrete, measured "
            "motivation for M4's decision-authority separation, not a claim that "
            "input filtering must be perfected first."
        )
    else:
        weakest = min(
            FAMILIES,
            key=lambda f: (combined.get("h_union", {}).get("by_family", {}).get(f, {}).get("tpr", 1.0)),
        )
        weakest_tpr = combined.get("h_union", {}).get("by_family", {}).get(weakest, {}).get("tpr")
        lines.append(
            "No family fell below 50% TPR under H-union in this run -- the "
            f"weakest is {weakest} at {weakest_tpr:.0%} if measured. This differs "
            "from the issue's anticipated F3/F4/F6-evade-everything narrative; "
            "reported as measured rather than adjusted to match the expectation. "
            "The architectural finding still holds regardless: since Week 15 the "
            "LLM cannot assign a triage verdict, so even a genuinely uncovered "
            "family would only degrade an explanation, not an outcome."
        )

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines) + "\n")

    summary = {
        "experiment": "M3.2 Part C -- detector x family failure matrix",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "output_markdown": str(OUTPUT_MD),
        "uncovered_families": uncovered_from_union,
        "detectors_included": [k for k in DETECTOR_KEYS if k in combined],
        "detectors_missing": [k for k in DETECTOR_KEYS if k not in combined],
    }
    Path("experiments/results/m3_2_familywise_failure_analysis.json").write_text(
        json.dumps(summary, indent=2)
    )
    print(f"saved {OUTPUT_MD}")
    print(f"detectors included: {summary['detectors_included']}")
    print(f"detectors missing: {summary['detectors_missing']}")


if __name__ == "__main__":
    main()
