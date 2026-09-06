# experiments/verdict_invariance_check.py
#
# The central architectural claim of this project is that the explanation node
# cannot change a triage verdict: classify_with_rf is the sole writer of
# predicted_label, and explain_with_llm runs strictly after the verdict and the
# review decision are both fixed. Everything downstream rests on it -- it is
# why a prompt injection carried inside an alert cannot flip an outcome, and it
# is what makes the LLM's measured 0.2823 accuracy irrelevant to the pipeline's
# result rather than fatal to it.
#
# Until Week 17 the paper evidenced that claim with a 299-alert live run whose
# artifact does not exist anywhere in this repository: control_node_ablation.json
# records `arm_a_vs_arm_b_verification: null` and `paired_mcnemar_tests: {}`,
# and only control_node_ablation_rows/arm_b.json survives. The run was killed
# by Groq's daily quota, the same limit that left ablation arms a, c and d
# incomplete. Rather than describe a run that cannot be inspected, this script
# re-establishes the claim in a form that is fully reproducible.
#
# It executes the real rf_primary graph -- every node, including the
# explanation node -- over all 999 alerts of the committed evaluation cache,
# and compares each graph verdict against the Random Forest's own
# predict_proba result for the same alert. The explanation call itself is
# skipped (SOC_COPILOT_SKIP_EXPLANATION=1), so the run is offline, free, and
# deterministic.
#
# What that does and does not establish, stated plainly:
#
#   IT DOES show, at n=999 (3.3x the vanished live run), that no node in the
#   deployed graph -- routing, guardrails, MITRE enrichment, context building,
#   the review gate, or the explanation node's own state update -- perturbs the
#   label the classifier assigned.
#
#   IT DOES NOT exercise a live LLM response body. That the explanation node
#   cannot write a label under ANY response is a structural property of its
#   return value, not a sampling question: explain_with_llm returns only
#   rationale/rationale_status/llm_response on all three of its exit paths.
#   tests/test_graph_wiring.py asserts exactly that, and asserts that the
#   explanation node runs after the verdict is fixed.
#
# Together those two -- a structural proof over the node's return type, and an
# end-to-end check over the whole graph at scale -- are a stronger and more
# checkable basis for the claim than the 299-alert run they replace.
#
# usage (from repo root, offline, no API key, ~1 minute):
#   venv/bin/python experiments/verdict_invariance_check.py

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set before importing the graph so the explanation node reads it at call time.
os.environ["SOC_COPILOT_SKIP_EXPLANATION"] = "1"

import numpy as np
import pandas as pd

from src.agent.fallback_classifier import _load_model, _to_feature_frame
from src.agent.graph import build_triage_graph
from src.data.schema import TARGET_COLUMN
from src.models.decision import resolve_label

CACHE_PATH = Path("experiments/results/evaluation_samples/guide_balanced_333_per_class_seed_42.csv")
OUTPUT_PATH = Path("experiments/results/verdict_invariance.json")


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def check(sample: pd.DataFrame) -> dict:
    graph = build_triage_graph(mode="rf_primary")
    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    mismatches: list[dict] = []
    errors: list[dict] = []
    ties = 0
    statuses: Counter[str] = Counter()
    paths: Counter[str] = Counter()
    review_flagged = 0

    for index, row in sample.iterrows():
        alert = row.to_dict()
        alert.pop(TARGET_COLUMN, None)

        proba = model.predict_proba(_to_feature_frame(alert, model, encoders))[0]
        offline_label = resolve_label(model.classes_, proba)

        # An exact tie between the top two classes is the one case where two
        # reasonable implementations disagree, so count them: a run with zero
        # ties would not have exercised the tie-break at all, and "0 mismatches"
        # would be a weaker result than it looks. See src/models/decision.py.
        ordered = np.sort(proba)[::-1]
        if len(ordered) > 1 and ordered[0] == ordered[1]:
            ties += 1

        try:
            result = graph.invoke({"raw_alert": alert})
        except Exception as exc:
            errors.append({"_row_index": int(index), "error": f"{type(exc).__name__}: {exc}"})
            continue

        statuses[result.get("rationale_status") or "none"] += 1
        paths[result.get("triage_path") or "none"] += 1
        if result.get("needs_human_review"):
            review_flagged += 1

        if result.get("predicted_label") != offline_label:
            mismatches.append(
                {
                    "_row_index": int(index),
                    "graph_label": result.get("predicted_label"),
                    "classifier_label": offline_label,
                    "probabilities": [round(float(p), 6) for p in proba],
                }
            )

    scored = len(sample) - len(errors)
    return {
        "n_alerts": len(sample),
        "n_scored": scored,
        "n_errors": len(errors),
        "errors": errors,
        "exact_probability_ties": ties,
        "verdict_mismatches": mismatches,
        "n_mismatches": len(mismatches),
        "verdicts_identical": len(mismatches) == 0 and not errors,
        "rationale_status_distribution": dict(statuses),
        "triage_path_distribution": dict(paths),
        "flagged_for_human_review": review_flagged,
    }


def main() -> None:
    if not CACHE_PATH.exists():
        raise SystemExit(
            f"{CACHE_PATH} is missing. It is committed to this repository; "
            f"if it is absent, regenerate it with "
            f"src.agent.evaluate.load_balanced_evaluation_sample(999)."
        )

    sample = pd.read_csv(CACHE_PATH).reset_index(drop=True)
    print(f"running the rf_primary graph over {len(sample)} alerts (explanation call skipped)...")
    result = check(sample)

    output = {
        "experiment": "Verdict invariance: does any node in the deployed graph alter the classifier's label?",
        "question": (
            "The paper claims the explanation node cannot change a verdict. This "
            "runs the whole rf_primary graph over the committed 999-alert "
            "evaluation cache and compares every verdict against the Random "
            "Forest's own predict_proba result for the same alert."
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "evaluation_sample": str(CACHE_PATH),
        "graph_mode": "rf_primary",
        "explanation_call": "skipped (SOC_COPILOT_SKIP_EXPLANATION=1) -- the node still executes",
        "tie_break": "src/models/decision.py, shared with the deployed path",
        "supersedes": (
            "The 299-alert live verification previously cited in the paper. Its "
            "artifact does not exist in this repository (control_node_ablation.json "
            "records arm_a_vs_arm_b_verification: null); the run was lost to Groq "
            "quota exhaustion. This check covers 3.3x as many alerts and is "
            "reproducible offline."
        ),
        "scope": (
            "This is an end-to-end check over the deployed graph, not a live-LLM "
            "check. That explain_with_llm cannot write a label under any response "
            "is a property of its return value, asserted structurally by "
            "tests/test_graph_wiring.py::test_explanation_node_cannot_set_a_verdict "
            "and ::test_verdict_is_assigned_before_the_llm_ever_runs."
        ),
        **result,
        "interpretation": (
            f"{result['n_scored'] - result['n_mismatches']}/{result['n_scored']} graph verdicts "
            f"are identical to the classifier's own prediction "
            f"({result['exact_probability_ties']} of them exact probability ties, where the "
            f"shared tie-break in src/models/decision.py is what makes them agree). "
            + (
                "No node in the pipeline alters the label the classifier assigned."
                if result["verdicts_identical"]
                else f"{result['n_mismatches']} mismatch(es) and {result['n_errors']} error(s) "
                     f"-- the architectural claim does not hold as stated and must be corrected."
            )
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))

    print(f"\n  alerts scored        : {result['n_scored']}/{result['n_alerts']}")
    print(f"  verdict mismatches   : {result['n_mismatches']}")
    print(f"  exact probability ties: {result['exact_probability_ties']}")
    print(f"  errors               : {result['n_errors']}")
    print(f"  flagged for review   : {result['flagged_for_human_review']}")
    print(f"\n{output['interpretation']}")
    print(f"\nsaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
