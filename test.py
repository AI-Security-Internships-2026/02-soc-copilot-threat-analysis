import pandas as pd
from src.agent.schema_guardrail import validate_field_types

# df = pd.read_csv("datasets/GUIDE_train.csv", usecols=["AlertTitle"])
# sample = df["AlertTitle"].sample(5000, random_state=42)
# false_positives = sum(bool(validate_field_types({"AlertTitle": v})) for v in sample)
# print(f"false positives on {len(sample)} real AlertTitle values: {false_positives}")
df = pd.read_csv("datasets/GUIDE_train.csv", usecols=["DetectorId"])
print(df["DetectorId"].sample(10, random_state=42).tolist())