"""
Deterministic schema/type guardrail for structured GUIDE alert fields.

Why this exists (issue #10, week 9 follow-up):
Week 8 tried a TF-IDF+LogReg text classifier scoped to AlertTitle as a second-stage
guardrail behind the regex fast-path, and found it had no usable signal on real
SOC alert data (best accuracy 52.5% across a threshold sweep).

Root cause, confirmed by direct inspection of the real GUIDE_train.csv (week 9):
AlertTitle is not text at all. it's a numeric ID field -- 86,149 unique values,
all plain integers (e.g. 45654, 99614, 111349). this matches the GUIDE paper's
own description of the alert dataframe: the only categorical columns it lists
are OrganizationId, DetectorId, ProductId, Category, and Severity, all
closed-vocabulary/numeric -- there's no free-text column in the schema at all.
a text classifier can't find linguistic signal in a field that was never
linguistic to begin with, so no amount of domain-matched training data would
have fixed it. the "fine-tune on SOC-domain text" plan (roadmap, Aug 9
milestone) is retired in favor of this.

correct check for a field whose legitimate values are always integers: verify
it IS an integer. any prompt-injection payload is, definitionally, not a valid
integer -- so this check separates the two classes by construction, not by
learned approximation, and costs microseconds instead of a model load.
"""

from __future__ import annotations

from typing import Any

# fields whose legitimate values are always numeric IDs per the real GUIDE
# schema (see datasets/README.md, schema.py, and the GUIDE paper's alert
# dataframe description -- AlertTitle and DetectorId are both numeric ID
# spaces in the actual data, not text).
EXPECTED_NUMERIC_FIELDS = {"AlertTitle", "DetectorId"}


def validate_field_types(alert: dict[str, Any]) -> list[str]:
    """Return reason codes for fields that should be numeric IDs but aren't.

    a field failing this check means it contains something other than a
    valid ID -- which is inherently suspicious regardless of what that
    "something" says, since the field was never supposed to carry free text.

    note: missing values come through as None (dict.get default) or as
    float('nan') if this ever runs directly against a pandas row -- both
    are treated as "nothing to check" here, matching how the rest of the
    pipeline already treats missing evidence (routes on signal count, not
    a hard failure). worth confirming that's still what you want once this
    runs against real rows with actual missing AlertTitle values.
    """
    reasons: list[str] = []
    for field in EXPECTED_NUMERIC_FIELDS:
        if field not in alert or alert[field] is None:
            continue
        value = alert[field]

        # already a real int/float -- fine, nothing to check
        # (isinstance(x, float) also passes NaN through untouched -- see note above)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            continue

        # strings are allowed IF they parse cleanly as an integer
        # (CSV loading, JSON, etc. can all hand us "45654" as a str)
        if isinstance(value, str):
            try:
                int(value.strip())
                continue
            except ValueError:
                reasons.append(f"non_numeric_field:{field}")
                continue

        # any other type (dict, list, etc.) is automatically invalid
        reasons.append(f"non_numeric_field:{field}")
    return reasons