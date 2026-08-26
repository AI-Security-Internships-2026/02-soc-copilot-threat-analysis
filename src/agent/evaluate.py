# src/agent/evaluate.py
# evaluates the LLM triage agent on a sample of alerts and compares
# its performance to the week 2 random forest baseline.
# uses the same metrics: accuracy + macro F1.

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, classification_report

from src.data.load_data import REAL_DATA_PATH, SAMPLE_DATA_PATH
from src.agent.graph import triage_graph


# map the IncidentGrade integers (from the preprocessed df) back to label strings.
# preprocess.py label-encodes IncidentGrade — we need the original string form.
# these match the GUIDE dataset's IncidentGrade values.
LABEL_MAP = {
    "TruePositive": "TruePositive",
    "BenignPositive": "BenignPositive",
    "FalsePositive": "FalsePositive",
}

SAMPLE_SEED = 42
SAMPLE_CACHE_DIR = Path("experiments/results/evaluation_samples")


def _active_data_path() -> Path:
    return REAL_DATA_PATH if REAL_DATA_PATH.exists() else SAMPLE_DATA_PATH


def _data_signature(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "size_bytes": stat.st_size, "modified_ns": stat.st_mtime_ns}


def load_balanced_evaluation_sample(sample_size: int, seed: int = SAMPLE_SEED) -> pd.DataFrame:
    """Return a cached, reproducible class-balanced sample without loading all data.

    The first run streams the CSV in chunks and keeps a reservoir sample for
    each class. Later runs reuse the small cache unless the source dataset,
    requested sample size, or seed changed.
    """
    sample_per_class = sample_size // 3
    path = _active_data_path()
    SAMPLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = SAMPLE_CACHE_DIR / f"guide_balanced_{sample_per_class}_per_class_seed_{seed}.csv"
    metadata_path = cache_path.with_suffix(".json")
    expected_metadata = {
        "data": _data_signature(path),
        "sample_per_class": sample_per_class,
        "seed": seed,
    }

    if cache_path.exists() and metadata_path.exists():
        with open(metadata_path) as file:
            if json.load(file) == expected_metadata:
                cached = pd.read_csv(cache_path)
                if len(cached) == sample_per_class * len(LABEL_MAP):
                    print(f"Reusing cached evaluation sample: {cache_path}")
                    return cached

    print(f"Creating a balanced evaluation sample by streaming {path}...")
    rng = np.random.default_rng(seed)
    reservoirs = {label: pd.DataFrame() for label in LABEL_MAP}
    rows_seen = 0
    for chunk_number, chunk in enumerate(pd.read_csv(path, chunksize=100_000), start=1):
        chunk = chunk.dropna(subset=["IncidentGrade"])
        rows_seen += len(chunk)
        for label in LABEL_MAP:
            candidates = chunk[chunk["IncidentGrade"] == label].copy()
            if candidates.empty:
                continue
            candidates["_sample_key"] = rng.random(len(candidates))
            reservoirs[label] = pd.concat([reservoirs[label], candidates], ignore_index=True).nsmallest(
                sample_per_class, "_sample_key"
            )
        if chunk_number % 10 == 0:
            print(f"  scanned {rows_seen:,} rows...", flush=True)

    missing = [label for label, sample in reservoirs.items() if len(sample) < sample_per_class]
    if missing:
        raise ValueError(f"Not enough examples for evaluation classes: {', '.join(missing)}")

    sample = pd.concat(reservoirs.values(), ignore_index=True).drop(columns="_sample_key")
    sample.to_csv(cache_path, index=False)
    with open(metadata_path, "w") as file:
        json.dump(expected_metadata, file, indent=2)
    print(f"Cached balanced evaluation sample: {cache_path}")
    return sample


def run_evaluation(sample_size: int = 50, output_path: str = "experiments/results/agent_metrics.json"):
    """
    runs the LLM agent on `sample_size` rows from the dataset.
    saves results to agent_metrics.json alongside baseline_metrics.json.

    we keep sample_size small (default 50) because each row = one LLM API call.
    with gpt-4o-mini at ~$0.00015/1K input tokens this costs < $0.10 for 50 rows.
    """
    print("loading evaluation sample...")
    sample_per_class = sample_size // 3
    sample_df = load_balanced_evaluation_sample(sample_size).reset_index(drop=True)

    print(f"evaluating agent on {len(sample_df)} alerts ({sample_per_class} per class)...")
    print("this makes one LLM API call per row — expect ~1-2 minutes for 50 rows.\n")

    y_true = []
    y_pred = []
    results_log = []
    error_count = 0
    no_verdict_count = 0

    for i, row in sample_df.iterrows():
        # build the raw_alert dict from the dataframe row
        raw_alert = row.to_dict()
        ground_truth = raw_alert.pop("IncidentGrade")  # remove target from input

        try:
            # run the full agent pipeline on this alert
            result = triage_graph.invoke({"raw_alert": raw_alert})
        except Exception as e:
            # A genuine crash inside triage_graph.invoke() itself (e.g. an
            # unhandled exception in a node) -- not a normal graph outcome, so
            # there's no state dict to inspect. Do NOT default predicted_label
            # to a real class here -- a fabricated "FalsePositive" would
            # silently feed into y_pred/metrics and produce a plausible-looking
            # accuracy number even if the pipeline is broken. Excluded from
            # y_true/y_pred; counted in routing_summary.error_count instead.
            predicted = None
            reasoning = f"agent crash: {str(e)}"
            confidence = "low"
            error = str(e)
            triage_path = "error"
            context_signal_count = None
            fallback_probability = None
            error_count += 1
            print(f"  [ERROR] row {i} crashed and was excluded from metrics: {e}")
        else:
            if not result.get("predicted_label"):
                if not result.get("needs_human_review"):
                    # The graph completed without raising AND without reaching
                    # any of the pipeline's legitimate no-verdict end states
                    # (guardrail block, handled RF/LLM failure -- both route
                    # through human_review_node, which always sets
                    # needs_human_review). No predicted_label and no
                    # needs_human_review means a node dead-ended silently --
                    # the exact Week 9 regression. This raise sits in the
                    # try/except's `else` clause, not the `try` body, so it is
                    # NOT caught by the `except Exception` above and actually
                    # propagates out of run_evaluation instead of being turned
                    # into a scored FalsePositive prediction.
                    raise RuntimeError(
                        f"triage_graph.invoke() returned no predicted_label and no "
                        f"needs_human_review flag for row {i} (keys present: "
                        f"{sorted(result.keys())}) -- likely a graph-wiring regression"
                    )
                # Legitimate no-automated-verdict outcome (guardrail-blocked,
                # or a handled RF/LLM failure routed to human review) -- not a
                # bug, but there's no real prediction to score either.
                predicted = None
                no_verdict_count += 1
            else:
                predicted = result["predicted_label"]

            reasoning = result.get("reasoning", "")
            confidence = result.get("confidence", "low")
            error = result.get("error", None)
            triage_path = result.get("triage_path", "llm")
            context_signal_count = result.get("context_signal_count", None)
            fallback_probability = result.get("fallback_probability", None)

        if predicted is not None:
            y_true.append(ground_truth)
            y_pred.append(predicted)

        # log each prediction for inspection
        results_log.append({
            "ground_truth": ground_truth,
            "predicted": predicted,
            "confidence": confidence,
            "reasoning": reasoning,
            "error": error,
            "triage_path": triage_path,
            "context_signal_count": context_signal_count,
            "fallback_probability": fallback_probability,
        })

        # print progress every 10 rows
        if len(results_log) % 10 == 0:
            print(f"  processed {len(results_log)}/{len(sample_df)} alerts...")

        # small sleep to avoid rate limits — adjust if needed
        time.sleep(0.3)

    if len(sample_df) and not y_true:
        # Nothing produced a scorable prediction -- either every row crashed
        # or every row hit a legitimate no-verdict outcome. Either way, refuse
        # to report metrics computed from zero successful predictions instead
        # of letting accuracy_score/f1_score raise an opaque error further down.
        raise RuntimeError(
            f"none of {len(sample_df)} rows produced a scorable prediction "
            f"(error_count={error_count}, no_verdict_count={no_verdict_count}) -- "
            "see per-row 'error'/'reasoning' fields for details."
        )

    if error_count:
        print(
            f"\nWARNING: {error_count}/{len(sample_df)} rows crashed and were excluded "
            "from accuracy/macro-F1 -- see routing_summary.error_count and the "
            "per_alert_results entries with triage_path == 'error'\n"
        )

    if no_verdict_count:
        print(
            f"\n{no_verdict_count}/{len(sample_df)} rows had no automated verdict "
            "(guardrail-blocked or a handled RF/LLM failure routed to human review) "
            "and were excluded from accuracy/macro-F1 -- see routing_summary.no_verdict_count\n"
        )

    # compute metrics (only over rows that produced a real prediction)
    accuracy = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    report = classification_report(y_true, y_pred, zero_division=0)

    print(f"\n=== agent evaluation results ===")
    print(f"accuracy:  {accuracy:.4f}")
    print(f"macro f1:  {macro_f1:.4f}")
    print(f"\nclassification report:\n{report}")

    # load baseline metrics for comparison
    baseline_path = Path("experiments/results/baseline_metrics.json")
    baseline_note = ""
    if baseline_path.exists():
        with open(baseline_path) as f:
            baseline = json.load(f)
        baseline_acc = baseline.get("classification_report", {}).get("accuracy", "N/A")
        baseline_f1 = baseline.get("macro_f1", "N/A")
        print(f"=== vs RF baseline ===")
        print(f"baseline accuracy: {baseline_acc}  →  agent accuracy: {accuracy:.4f}")
        print(f"baseline macro f1: {baseline_f1}  →  agent macro f1: {macro_f1:.4f}")
        baseline_note = f"RF baseline: acc={baseline_acc}, f1={baseline_f1}"

    # save results
    output = {
        "sample_size": len(sample_df),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "baseline_comparison": baseline_note,
        "per_alert_results": results_log,
    }

    fallback_count = sum(item["triage_path"] == "rf_fallback" for item in results_log)
    output["routing_summary"] = {
        "rf_fallback_count": fallback_count,
        "llm_count": sum(item["triage_path"] == "llm" for item in results_log),
        "error_count": error_count,
        "error_rate": round(error_count / len(results_log), 4) if results_log else 0.0,
        "no_verdict_count": no_verdict_count,
        "fallback_rate": round(fallback_count / len(results_log), 4) if results_log else 0.0,
        "scored_count": len(y_true),
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nresults saved to {output_path}")
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="evaluate the SOC Co-pilot agent on GUIDE alerts")
    parser.add_argument("--sample-size", type=int, default=50, help="total alerts to sample (split evenly across 3 classes)")
    parser.add_argument("--output", type=str, default="experiments/results/agent_metrics.json", help="path to save results json")
    args = parser.parse_args()

    run_evaluation(sample_size=args.sample_size, output_path=args.output)
