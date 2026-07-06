# src/agent/run_agent.py
# quick entrypoint to run a single alert through the triage agent manually.
# useful for testing and demoing to supervisors.
# run with: python src/agent/run_agent.py

from src.agent.graph import triage_graph


def run_single_alert(alert: dict) -> None:
    """
    runs one alert through the full agent pipeline and prints the verdict.
    """
    print("running agent on alert...")
    print(f"input: {alert}\n")

    result = triage_graph.invoke({"raw_alert": alert})

    print("=== agent verdict ===")
    print(f"predicted label: {result.get('predicted_label')}")
    print(f"confidence:      {result.get('confidence')}")
    print(f"reasoning:       {result.get('reasoning')}")

    if result.get("error"):
        print(f"error:           {result['error']}")


if __name__ == "__main__":
    # example alert matching GUIDE schema fields
    # you can swap this with a real row from GUIDE_train.csv
    example_alert = {
        "AlertTitle": "Suspicious PowerShell execution detected",
        "Category": "Execution",
        "MitreTechniques": "T1059.001",
        "DetectorId": "MDECustomAlerts",
        "Hour": 2,           # 2am — unusual hour
        "DayOfWeek": 0,      # monday
        "SuspicionLevel": "High",
        "LastVerdict": "Suspicious",
    }

    run_single_alert(example_alert)