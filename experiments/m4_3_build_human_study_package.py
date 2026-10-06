# experiments/m4_3_build_human_study_package.py
#
# Issue #40 (M4.3), PART A. Builds the complete human-study package the
# supervisor distributes to 5 raters: the stratified 100-alert sample, both
# explanation variants per alert, the blinded rating sheets, and the A/B key
# that is withheld from raters.
#
# Mirrors the M3.1 rater packet (experiments/m3_1_build_rating_worksheet.py,
# docs/m3-1-rater-instructions.md) that was accepted on issue #35: identical
# items in identical order across every rater sheet, a pre-filled `rater`
# column so a returned file is self-identifying, a free-text note column, and
# the answer key in a separate dot-prefixed file that is committed for
# reproducibility but never distributed.
#
# Three stages, because only the middle one needs a live model:
#
#   1  --sample              offline. Draws the stratified sample from
#                            GUIDE_Test and records each alert's RF verdict.
#   2  --generate-explanations
#                            LIVE. Invokes the real A4 graph per alert and
#                            keeps its `rationale`. Checkpointed after every
#                            alert, so a quota stall resumes instead of
#                            restarting. Variant X needs no model at all.
#   3  --build-sheets        offline. Blinds, shuffles, and writes the five
#                            rater sheets plus the key.
#
# `--all` runs all three. usage (from repo root):
#   venv/bin/python experiments/m4_3_build_human_study_package.py --sample
#   venv/bin/python experiments/m4_3_build_human_study_package.py --generate-explanations
#   venv/bin/python experiments/m4_3_build_human_study_package.py --build-sheets
#
# Deliberately NOT here: Fleiss' kappa, the Wilcoxon test, and the Spearman
# cross-validation against PART B's proxies. No ratings exist yet, and a
# scoring script that can run before its input arrives is a script that can
# manufacture a number. Scoring is written when the completed sheets come back
# (issue #40, supervisor item 2).

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

GUIDE_TEST = Path("datasets/GUIDE_Test.csv")
SAMPLE_PATH = Path("experiments/results/m4_3_study_alerts.csv")
EXPLANATIONS_PATH = Path("experiments/results/m4_3_explanations.json")
KEY_PATH = Path("experiments/results/.m4_3_variant_key.csv")
SHEET_DIR = Path("experiments/results")
RATERS = ["A", "B", "C", "D", "E"]

#: Issue #40: TP=34, BP=33, FP=33, approximately balanced over 100 alerts.
STRATA = {"TruePositive": 34, "BenignPositive": 33, "FalsePositive": 33}
SEED = 42

#: The fields build_context() puts in the prompt. These are what a rater is
#: shown, so an explanation is judged against exactly the evidence that
#: produced it and nothing more.
EVIDENCE_COLUMNS = [
    "AlertTitle", "Category", "MitreTechniques", "DetectorId",
    "SuspicionLevel", "LastVerdict",
]

#: Columns this script adds on top of the GUIDE row, so stage 2 can strip them
#: back off and hand the classifier the same raw alert the deployed pipeline
#: gets. Feeding it only EVIDENCE_COLUMNS changed a third of the verdicts.
DERIVED_COLUMNS = ["item_id", "ground_truth", "rf_verdict", "rf_probability", "rf_margin"]

DIMENSIONS = ["faithfulness", "factual_correctness", "analyst_usefulness", "no_unsupported_claims"]


def _sample() -> None:
    """Stratified 100-alert draw from GUIDE_Test, with each alert's RF verdict."""
    from src.agent.fallback_classifier import predict_with_margin

    frame = pd.read_csv(GUIDE_TEST, low_memory=False)
    frame = frame[frame["IncidentGrade"].isin(STRATA)]

    # Deduplicate on the evidence a rater is actually shown, before sampling.
    # build_context() surfaces six low-cardinality fields, so 100 distinct GUIDE
    # rows collapsed to 57 distinct rating tasks -- one appeared 16 times. That
    # inflates Fleiss' kappa (a rater trivially agrees with themselves on
    # identical text) and makes the 100 Wilcoxon pairs non-independent. 47,415
    # distinct combinations exist in GUIDE_Test, so nothing is strained by
    # requiring 100 of them. Deviates from a literal reading of issue #40's
    # "100 stratified alerts"; recorded on the issue rather than done quietly.
    frame = frame.drop_duplicates(subset=EVIDENCE_COLUMNS)

    parts = []
    for grade, n in STRATA.items():
        stratum = frame[frame["IncidentGrade"] == grade]
        if len(stratum) < n:
            raise SystemExit(f"GUIDE_Test has only {len(stratum)} distinct {grade} alerts; need {n}")
        parts.append(stratum.sample(n=n, random_state=SEED))
    sample = pd.concat(parts).sample(frac=1.0, random_state=SEED).reset_index(drop=True)

    # Every GUIDE column is kept, not just the six that get displayed: the
    # deployed pipeline classifies the full row, and a subset predicts
    # differently.
    sample.insert(0, "item_id", [f"E{i:03d}" for i in range(1, len(sample) + 1)])
    sample["ground_truth"] = sample["IncidentGrade"]
    verdicts = [predict_with_margin(record) for record in sample.to_dict("records")]
    sample["rf_verdict"] = [v[0] for v in verdicts]
    sample["rf_probability"] = [round(float(v[1]), 4) for v in verdicts]
    sample["rf_margin"] = [round(float(v[2]), 4) for v in verdicts]

    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(SAMPLE_PATH, index=False)
    counts = sample["ground_truth"].value_counts().to_dict()
    print(f"saved {SAMPLE_PATH} ({len(sample)} alerts, strata {counts}, seed {SEED})")


def _load_sample() -> list[dict]:
    """Read back through pandas, not csv, so numeric fields come back as
    numbers. Reading the same row as strings is enough to move a prediction."""
    if not SAMPLE_PATH.exists():
        raise SystemExit(f"{SAMPLE_PATH} missing -- run with --sample first")
    return pd.read_csv(SAMPLE_PATH, low_memory=False).to_dict("records")


def _raw_alert(row: dict) -> dict:
    """The GUIDE row as the deployed pipeline receives it."""
    return {k: v for k, v in row.items() if k not in DERIVED_COLUMNS and pd.notna(v)}


def _shown_evidence(row: dict) -> str:
    return "; ".join(
        f"{col}={row[col]}" for col in EVIDENCE_COLUMNS if pd.notna(row.get(col))
    )


def _baseline_variant(row: dict) -> str:
    """Variant X, exactly as issue #40 specifies it: `Alert <ID> classified as
    <LABEL>.` A bare stub with no evidence and no reasoning.

    Worth knowing before raters spend 90 minutes: this is a one-line stub and
    variant Y is 2-3 sentences of prose, so no amount of shuffling makes the
    two arms indistinguishable to a reader. See the limitation recorded on
    issue #40 -- the comparison establishes that the proposed explanation beats
    having no explanation, which is a floor, not that it beats a reasonable
    alternative.
    """
    alert_id = row.get("AlertId") if pd.notna(row.get("AlertId")) else row["item_id"]
    return f"Alert {alert_id} classified as {row['rf_verdict']}."


def _generate_explanations() -> None:
    """Variant Y: the real A4 graph's rationale, checkpointed per alert.

    Invokes build_triage_graph("rf_primary") rather than re-implementing the
    prompt, so what raters score is the deployed pipeline's actual output --
    MITRE enrichment, guardrails and all -- not a copy that can drift from it.
    """
    from src.agent.graph import build_triage_graph

    rows = _load_sample()
    done = json.loads(EXPLANATIONS_PATH.read_text()) if EXPLANATIONS_PATH.exists() else {}
    if os.getenv("SOC_COPILOT_SKIP_EXPLANATION") == "1":
        raise SystemExit("SOC_COPILOT_SKIP_EXPLANATION=1 would return empty rationales")

    graph = build_triage_graph("rf_primary")
    for row in rows:
        item_id = row["item_id"]
        if done.get(item_id, {}).get("rationale"):
            continue
        result = graph.invoke({"raw_alert": _raw_alert(row)})
        done[item_id] = {
            "rationale": result.get("rationale"),
            "rationale_status": result.get("rationale_status"),
            "predicted_label": result.get("predicted_label"),
        }
        # Written every iteration: a rate limit halfway through must not throw
        # away the calls already paid for.
        EXPLANATIONS_PATH.write_text(json.dumps(done, indent=2) + "\n")
        print(f"{item_id}: {done[item_id]['rationale_status']}")

    missing = [r["item_id"] for r in rows if not done.get(r["item_id"], {}).get("rationale")]
    print(f"saved {EXPLANATIONS_PATH} ({len(rows) - len(missing)}/{len(rows)} explained)")
    if missing:
        print(f"still unexplained ({len(missing)}): {', '.join(missing)} -- rerun to resume")


def _build_sheets() -> None:
    """Blind, shuffle, and write the five rater sheets plus the withheld key."""
    rows = _load_sample()
    if not EXPLANATIONS_PATH.exists():
        raise SystemExit(f"{EXPLANATIONS_PATH} missing -- run with --generate-explanations first")
    explanations = json.loads(EXPLANATIONS_PATH.read_text())

    unexplained = [r["item_id"] for r in rows if not explanations.get(r["item_id"], {}).get("rationale")]
    if unexplained:
        raise SystemExit(
            f"{len(unexplained)} alerts have no proposed explanation: "
            f"{', '.join(unexplained)}. Sheets are not built from a partial set -- "
            "a missing variant silently drops that alert's pair from the paired test."
        )

    # The verdict shown to a rater must be the verdict the explanation is
    # explaining. These diverged on 34 of 100 alerts when stage 2 classified a
    # six-field subset instead of the full row; raters would have scored a third
    # of the corpus for unfaithfulness that was ours, not the model's.
    divergent = [
        r["item_id"] for r in rows
        if explanations[r["item_id"]]["predicted_label"] != r["rf_verdict"]
    ]
    if divergent:
        raise SystemExit(
            f"{len(divergent)} alerts have an explanation of a different verdict than "
            f"the sample records: {', '.join(divergent[:10])}"
            f"{' ...' if len(divergent) > 10 else ''}. Re-run --generate-explanations."
        )

    # One shared randomisation across all five raters. Per-rater mappings would
    # make the items non-identical, and Fleiss' kappa needs every rater scoring
    # the same item.
    rng = random.Random(SEED)
    items, key_rows = [], []
    for row in rows:
        variants = [("baseline", _baseline_variant(row)),
                    ("proposed", explanations[row["item_id"]]["rationale"])]
        rng.shuffle(variants)
        for shown_as, (source, text) in zip(["A", "B"], variants):
            items.append({
                "item_id": row["item_id"],
                "variant_shown": shown_as,
                "alert_evidence": _shown_evidence(row),
                "assigned_verdict": row["rf_verdict"],
                "explanation_text": text,
            })
            key_rows.append({
                "item_id": row["item_id"],
                "variant_shown": shown_as,
                "variant_source": source,
                "ground_truth": row["ground_truth"],
                "rf_verdict": row["rf_verdict"],
            })

    # Shuffled so an alert's two variants are not adjacent. This does not make
    # the arms indistinguishable -- see docs/m4-3-rater-instructions.md and the
    # limitation recorded on issue #40 -- it only stops them being presented as
    # an explicit side-by-side comparison.
    rng.shuffle(items)

    fieldnames = ["rater", "row_id", "item_id", "variant_shown", "alert_evidence",
                  "assigned_verdict", "explanation_text", *DIMENSIONS, "rater_note"]
    for rater in RATERS:
        path = SHEET_DIR / f"m4_3_rating_sheet_rater{rater}.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for position, item in enumerate(items, start=1):
                writer.writerow({
                    "rater": rater,
                    "row_id": f"R{position:03d}",
                    **item,
                    **{d: "" for d in DIMENSIONS},
                    "rater_note": "",
                })
        print(f"saved {path} ({len(items)} rows, rater {rater} copy)")

    with open(KEY_PATH, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(key_rows)
    print(f"saved {KEY_PATH} (A/B mapping -- NOT for distribution to raters)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true", help="stage 1, offline")
    parser.add_argument("--generate-explanations", action="store_true", help="stage 2, LIVE model calls")
    parser.add_argument("--build-sheets", action="store_true", help="stage 3, offline")
    parser.add_argument("--all", action="store_true", help="all three stages in order")
    args = parser.parse_args()

    if not any([args.sample, args.generate_explanations, args.build_sheets, args.all]):
        parser.error("pick at least one stage (--sample / --generate-explanations / --build-sheets / --all)")

    if args.sample or args.all:
        _sample()
    if args.generate_explanations or args.all:
        _generate_explanations()
    if args.build_sheets or args.all:
        _build_sheets()


if __name__ == "__main__":
    main()
