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

    for i, row in sample_df.iterrows():
        # build the raw_alert dict from the dataframe row
        raw_alert = row.to_dict()
        ground_truth = raw_alert.pop("IncidentGrade")  # remove target from input

        try:
            # run the full agent pipeline on this alert
            result = triage_graph.invoke({"raw_alert": raw_alert})

            if "predicted_label" not in result:
                # A missing verdict means a graph-wiring problem (a node dead-ended
                # without reaching classification), not a benign default case -- see
                # the Week 9 regression where this exact gap silently produced an
                # all-FalsePositive collapse instead of an error. Fail loudly instead.
                raise RuntimeError(
                    f"triage_graph.invoke() returned no predicted_label for row {i} "
                    f"(keys present: {sorted(result.keys())}) -- likely a graph-wiring regression"
                )

            predicted = result["predicted_label"]
            reasoning = result.get("reasoning", "")
            confidence = result.get("confidence", "low")
            error = result.get("error", None)
            triage_path = result.get("triage_path", "llm")
            context_signal_count = result.get("context_signal_count", None)
            fallback_probability = result.get("fallback_probability", None)

        except Exception as e:
            predicted = "FalsePositive"
            reasoning = f"agent crash: {str(e)}"
            confidence = "low"
            error = str(e)
            triage_path = "error"
            context_signal_count = None
            fallback_probability = None

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
        if (len(y_true)) % 10 == 0:
            print(f"  processed {len(y_true)}/{len(sample_df)} alerts...")

        # small sleep to avoid rate limits — adjust if needed
        time.sleep(0.3)

    # compute metrics
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
        "fallback_rate": round(fallback_count / len(results_log), 4) if results_log else 0.0,
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
