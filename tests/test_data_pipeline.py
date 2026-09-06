"""Tests for the data path: loading, preprocessing, and the RF fallback.

Before this file, src/data/{load_data,preprocess,schema}.py,
src/models/baseline.py and src/agent/fallback_classifier.py had no test
coverage at all -- the entire path from CSV to feature vector to prediction,
including the encoder round-trip that every reported accuracy figure depends
on, was unexercised.

Nothing here needs the 2.4GB GUIDE download or the 590MB model artifact; the
frames are built inline so the suite still runs on a fresh clone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data.preprocess import (
    encode_categoricals,
    engineer_timestamp_features,
    preprocess,
    transform_with_encoders,
)
from src.data.schema import ID_COLUMNS, TARGET_COLUMN


def _frame(n: int = 6) -> pd.DataFrame:
    """A GUIDE-shaped frame: identifiers, a timestamp, categoricals, a label."""
    return pd.DataFrame(
        {
            "Id": range(n),
            "OrgId": [1, 1, 2, 2, 3, 3][:n],
            "IncidentId": [10, 10, 20, 20, 30, 30][:n],
            "AlertId": range(100, 100 + n),
            "DetectorId": [5] * n,
            "DeviceId": range(200, 200 + n),
            "Timestamp": ["2024-01-15T08:30:00Z"] * n,
            "Category": ["Execution", "Impact"] * (n // 2),
            "SuspicionLevel": ["Suspicious", "Clean"] * (n // 2),
            TARGET_COLUMN: ["TruePositive", "BenignPositive", "FalsePositive"] * (n // 3),
        }
    )


class TestPreprocess:
    def test_identifier_columns_are_dropped(self):
        X, _, _ = preprocess(_frame())
        for column in ID_COLUMNS:
            assert column not in X.columns, f"{column} should be dropped as an identifier"

    def test_target_is_separated_from_features(self):
        X, y, _ = preprocess(_frame())
        assert TARGET_COLUMN not in X.columns
        assert len(y) == len(X)

    def test_timestamp_becomes_three_cyclical_features(self):
        out = engineer_timestamp_features(_frame())
        assert "Timestamp" not in out.columns
        assert {"Hour", "DayOfWeek", "Month"} <= set(out.columns)
        assert out["Hour"].iloc[0] == 8
        assert out["Month"].iloc[0] == 1

    def test_rows_with_a_missing_label_are_dropped(self):
        frame = _frame()
        frame.loc[0, TARGET_COLUMN] = np.nan
        X, y, _ = preprocess(frame)
        assert len(X) == len(frame) - 1
        assert y.isna().sum() == 0


class TestEncoderRoundTrip:
    """transform_with_encoders is what every inference path relies on."""

    def test_known_values_round_trip_to_their_training_codes(self):
        frame = pd.DataFrame({"Category": ["Execution", "Impact", "Execution"]})
        encoded, encoders = encode_categoricals(frame)
        again = transform_with_encoders(frame, encoders)
        assert list(again["Category"]) == list(encoded["Category"])

    def test_unseen_category_maps_to_the_sentinel_not_a_crash(self):
        """The -1 sentinel is load-bearing: guide_test_holdout_eval.py reports
        an 'unknown category rate' computed from it, and a crash here would
        take down the triage graph on any genuinely new value."""
        train = pd.DataFrame({"Category": ["Execution", "Impact"]})
        _, encoders = encode_categoricals(train)
        out = transform_with_encoders(pd.DataFrame({"Category": ["NeverSeenBefore"]}), encoders)
        assert out["Category"].iloc[0] == -1

    def test_missing_column_is_filled_rather_than_raising(self):
        """Sparse alerts (Wazuh, the demo app) omit most GUIDE fields."""
        train = pd.DataFrame({"Category": ["Execution"]})
        _, encoders = encode_categoricals(train)
        out = transform_with_encoders(pd.DataFrame({"Other": [1]}), encoders)
        assert "Category" in out.columns
        assert out["Category"].iloc[0] == -1

    def test_null_value_maps_to_the_sentinel(self):
        train = pd.DataFrame({"Category": ["Execution", "Impact"]})
        _, encoders = encode_categoricals(train)
        out = transform_with_encoders(pd.DataFrame({"Category": [None]}), encoders)
        assert out["Category"].iloc[0] == -1


class TestLoadAlerts:
    def test_missing_guide_columns_are_rejected(self, tmp_path):
        """A file that parses as CSV but isn't GUIDE should fail loudly."""
        from src.data.load_data import load_alerts

        bad = tmp_path / "not_guide.csv"
        bad.write_text("a,b\n1,2\n")
        with pytest.raises(ValueError, match="missing expected GUIDE columns"):
            load_alerts(path=bad)

    def test_absent_path_raises_with_a_recovery_hint(self, tmp_path):
        from src.data.load_data import load_alerts

        with pytest.raises(FileNotFoundError, match="generate_sample"):
            load_alerts(path=tmp_path / "nope.csv")


class TestFallbackRouting:
    """should_use_fallback decides which model sees an alert, so its
    boundary is a routing decision, not a detail."""

    def test_sparse_alert_routes_to_the_classifier(self):
        from src.agent.fallback_classifier import should_use_fallback

        assert should_use_fallback({"AlertTitle": 42}) is True

    def test_two_evidence_fields_are_enough_to_skip_the_fallback(self):
        from src.agent.fallback_classifier import evidence_field_count, should_use_fallback

        alert = {"SuspicionLevel": "Suspicious", "LastVerdict": "Malicious"}
        assert evidence_field_count(alert) == 2
        assert should_use_fallback(alert) is False

    def test_nan_does_not_count_as_evidence(self):
        """GUIDE rows carry float('nan') for absent fields; counting those as
        present would route sparse alerts as if they were well-evidenced."""
        from src.agent.fallback_classifier import evidence_field_count

        alert = {"SuspicionLevel": float("nan"), "LastVerdict": "Malicious"}
        assert evidence_field_count(alert) == 1
