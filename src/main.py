"""
SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage
CNIT/PNTLab Pisa — AI Security Internship 2026

Entry point. Runs the alert-triage pipeline end to end:
  load data -> preprocess -> train/evaluate baseline classifier

By default this runs against the local synthetic sample
(datasets/sample/guide_sample.csv). Once the real GUIDE dataset is
downloaded (see datasets/README.md), it's picked up automatically.

See docs/proposal.md for research objectives and architecture.
"""

import sys
from pathlib import Path

# Allow `python src/main.py` (per README) as well as `python -m src.main`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.baseline import train_and_evaluate

PROJECT_NAME = "SOC Co-pilot: LLM-Assisted Threat Analysis and Alert Triage"
ORGANISATION = "CNIT/PNTLab Pisa, TECIP, Scuola Superiore Sant'Anna"
STATUS = "Week 2 — data pipeline + baseline triage classifier"


def main() -> None:
    print("=" * 60)
    print(f"Project : {PROJECT_NAME}")
    print(f"Org     : {ORGANISATION}")
    print(f"Status  : {STATUS}")
    print("=" * 60)
    print()

    train_and_evaluate()


if __name__ == "__main__":
    main()
