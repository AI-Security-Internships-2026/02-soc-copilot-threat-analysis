# src/agent/evaluate.py
# evaluates the LLM triage agent on a sample of alerts and compares
# its performance to the week 2 random forest baseline.
# uses the same metrics: accuracy + macro F1.

import json
import time
from pathlib import Path

from sklearn.metrics import accuracy_score, f1_score, classification_report

from src.data.load_data import load_alerts
from src.data.preprocess import preprocess
from src.agent.graph import triage_graph


# map the IncidentGrade integers (from the preprocessed df) back to label strings.
# preprocess.py label-encodes IncidentGrade — we need the original string form.
# these match the GUIDE dataset's IncidentGrade values.
LABEL_MAP = {
    "TruePositive": "TruePositive",
    "BenignPositive": "BenignPositive",
    "FalsePositive": "FalsePositive",
}


def run_evaluation(sample_size: int = 50, output_path: str = "experiments/results/agent_metrics.json"):
    """
    runs the LLM agent on `sample_size` rows from the dataset.
    saves results to agent_metrics.json alongside baseline_metrics.json.

    we keep sample_size small (default 50) because each row = one LLM API call.
    with gpt-4o-mini at ~$0.00015/1K input tokens this costs < $0.10 for 50 rows.
    """
    print(f"loading data...")
    df_raw = load_alerts()

    # preprocess gives us numeric features — but we also need original string columns
    # for the LLM context. so we work with df_raw directly for alert building,
    # and use the IncidentGrade column (before encoding) as ground truth.
    df_raw = df_raw.dropna(subset=["IncidentGrade"])

    # sample evenly across all 3 classes so evaluation isn't skewed
    sample_per_class = sample_size // 3
    sampled_frames = []
    for grade in ["TruePositive", "BenignPositive", "FalsePositive"]:
        class_df = df_raw[df_raw["IncidentGrade"] == grade]
        n = min(sample_per_class, len(class_df))
        sampled_frames.append(class_df.sample(n=n, random_state=42))

    sample_df = sampled_frames[0]._append(sampled_frames[1])._append(sampled_frames[2]).reset_index(drop=True)

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

            predicted = result.get("predicted_label", "FalsePositive")
            reasoning = result.get("reasoning", "")
            confidence = result.get("confidence", "low")
            error = result.get("error", None)

        except Exception as e:
            predicted = "FalsePositive"
            reasoning = f"agent crash: {str(e)}"
            confidence = "low"
            error = str(e)

        y_true.append(ground_truth)
        y_pred.append(predicted)

        # log each prediction for inspection
        results_log.append({
            "ground_truth": ground_truth,
            "predicted": predicted,
            "confidence": confidence,
            "reasoning": reasoning,
            "error": error,
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
        baseline_acc = baseline.get("accuracy", "N/A")
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

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nresults saved to {output_path}")
    return output


if __name__ == "__main__":
    run_evaluation()