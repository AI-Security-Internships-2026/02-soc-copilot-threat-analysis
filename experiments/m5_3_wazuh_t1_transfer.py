"""
M5.2 PART A -- Wazuh Tier-1 cross-domain schema transfer.

Issue #43. The issue asks for a transfer *accuracy retention* figure: score the
pipeline on 10,000 GUIDE-schema synthetic alerts, again on the same incidents
expressed as Wazuh JSON, and report the delta.

**That experiment, run literally, would produce a meaningless number, so this
does not run it.** `src/data/generate_sample.py` assigns `IncidentGrade` with
`random.choices(TARGET_CLASSES, weights=[...])` -- drawn independently of every
feature. Verified here, not assumed (see `label_learnability_check`): a
5-fold RandomForest scores 0.3470 on the synthetic labels against a 0.4028
majority-class floor. It cannot beat a constant answer, because there is no
signal to learn. Both sides of an accuracy comparison would therefore be chance,
"retention" would land near 100%, and the issue's own acceptance criterion
(>= 85% retention) would pass while measuring nothing. The repository has been
caught by exactly this once already -- `experiments/results/archive/` carries
`agent_metrics.json`, withdrawn for being a synthetic-data run whose labels are
random noise.

**What is measured instead is label-free and answers the real question.** The
useful thing to know about an adapter is not "is it accurate" -- accuracy needs
labels nobody has -- but *does it preserve the information the classifier acts
on*. So the same synthetic incident is put through the pipeline twice: once as a
native GUIDE row, once round-tripped GUIDE -> Wazuh JSON -> adapter ->
raw_alert. Ground truth never enters. Reported:

  * verdict agreement between the two paths, with a 95% CI
  * per-field survival across the round trip
  * schema-guardrail pass rate on adapter output
  * pipeline completion rate (no error, verdict produced)

Verdict agreement is a genuine transfer-fidelity measurement: if the adapter
drops a field the classifier weights, the two paths diverge and the number
falls. Nothing here claims Wazuh production accuracy, and nothing can, because
no labelled Wazuh data exists.

Run:  venv/bin/python experiments/m5_3_wazuh_t1_transfer.py
      venv/bin/python experiments/m5_3_wazuh_t1_transfer.py --n 10000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.fallback_classifier import _load_model, _to_feature_frame
from src.agent.schema_guardrail import validate_field_types
from src.data.generate_sample import generate
from src.integrations.wazuh_adapter import wazuh_alert_to_raw_alert
from src.models.decision import resolve_label

OUT = Path("experiments/results/m5_3_wazuh_t1.json")

# Wazuh buckets rule.level 0-15 into low/medium/high; invert the adapter's own
# thresholds so a GUIDE SuspicionLevel survives the trip rather than being lost.
_LEVEL_FOR = {"high": 13, "medium": 9, "low": 3}


def git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> dict:
    alpha = 1 - confidence
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return {"point": round(k / n, 4), "ci_lower": round(lo, 4),
            "ci_upper": round(hi, 4), "k": k, "n": n,
            "method": "exact Clopper-Pearson binomial interval"}


def label_learnability_check(df: pd.DataFrame) -> dict:
    """Is there any signal in the synthetic labels? Establishes, rather than
    asserts, why no accuracy comparison is reported."""
    y = df["IncidentGrade"]
    X = df.drop(columns=["IncidentGrade", "Timestamp"]).copy()
    for c in X.columns:
        if X[c].dtype == object or X[c].isna().any():
            X[c] = LabelEncoder().fit_transform(X[c].astype(str))
    scores = cross_val_score(RandomForestClassifier(n_estimators=100, random_state=0),
                             X, y, cv=5, scoring="accuracy")
    floor = float(y.value_counts(normalize=True).max())
    return {
        "cv_accuracy_mean": round(float(scores.mean()), 4),
        "cv_accuracy_std": round(float(scores.std()), 4),
        "majority_class_floor": round(floor, 4),
        "labels_are_learnable": bool(scores.mean() > floor + 0.03),
        "interpretation": (
            "A RandomForest cannot beat a constant answer on these labels, so "
            "they carry no signal. Any accuracy comparison built on them would "
            "compare chance with chance."),
    }


def guide_row_to_wazuh(row: dict) -> dict:
    """Express a GUIDE row as Wazuh alert JSON. Only fields the adapter reads
    are emitted; inventing richer Wazuh structure the adapter ignores would
    flatter the round trip without changing what reaches the classifier."""
    techniques = row.get("MitreTechniques")
    ids = [t.strip() for t in str(techniques).replace(";", ",").split(",")
           if t and t.strip() and t.strip().lower() != "nan"]
    groups = [g.strip() for g in str(row.get("Category") or "").split(",") if g.strip()]
    level = _LEVEL_FOR.get(str(row.get("SuspicionLevel") or "").lower())

    alert: dict = {
        "rule": {
            "id": int(row["AlertTitle"]) if pd.notna(row.get("AlertTitle")) else None,
            "description": f"synthetic rule {row.get('AlertTitle')}",
            "groups": groups,
        },
        "agent": {"id": "001", "name": str(row.get("DeviceName") or "unknown")},
    }
    if ids:
        alert["rule"]["mitre"] = {"id": ids}
    if level is not None:
        alert["rule"]["level"] = level
    if row.get("Timestamp"):
        alert["timestamp"] = str(row["Timestamp"])
    return alert


def verdict_for(alert: dict, model, encoders) -> tuple[str | None, float | None, str | None]:
    try:
        proba = model.predict_proba(_to_feature_frame(dict(alert), model, encoders))[0]
        ordered = np.sort(proba)[::-1]
        return resolve_label(model.classes_, proba), float(ordered[0] - ordered[1]), None
    except Exception as exc:                      # surfaced, never silently dropped
        return None, None, f"{type(exc).__name__}: {exc}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f"generating {args.n} synthetic GUIDE-schema alerts (seed {args.seed})...")
    df = generate(args.n, seed=args.seed)

    print("checking whether the synthetic labels carry any signal...")
    learnability = label_learnability_check(df)
    print(f"    cv acc {learnability['cv_accuracy_mean']} vs floor "
          f"{learnability['majority_class_floor']} -> learnable="
          f"{learnability['labels_are_learnable']}")

    artifact = _load_model()
    model, encoders = artifact["model"], artifact["encoders"]

    # Fields the adapter is capable of carrying. Anything outside this set is
    # dropped by construction, which is a documented limitation, not a bug.
    ADAPTER_FIELDS = ["AlertTitle", "DetectorId", "Category",
                      "MitreTechniques", "SuspicionLevel", "Hour", "DayOfWeek"]

    agree = 0, 0
    n_agree = n_compared = 0
    schema_pass = pipeline_ok = 0
    field_survived = {f: 0 for f in ADAPTER_FIELDS}
    field_present = {f: 0 for f in ADAPTER_FIELDS}
    native_errors = wazuh_errors = 0
    margin_deltas = []

    print("round-tripping GUIDE -> Wazuh JSON -> adapter -> raw_alert...")
    for _, row in df.iterrows():
        native = row.to_dict()
        native.pop("IncidentGrade", None)

        wazuh_json = guide_row_to_wazuh(native)
        mapped = wazuh_alert_to_raw_alert(wazuh_json)

        if not validate_field_types(mapped):
            schema_pass += 1

        for f in ADAPTER_FIELDS:
            nv = native.get(f)
            if nv is not None and str(nv).lower() != "nan" and str(nv) != "":
                field_present[f] += 1
                mv = mapped.get(f)
                if mv is not None and str(mv) != "":
                    # MitreTechniques changes separator (';' -> ', '); compare
                    # as a set of ids rather than as a string.
                    if f == "MitreTechniques":
                        a = {t.strip() for t in str(nv).replace(";", ",").split(",") if t.strip()}
                        b = {t.strip() for t in str(mv).replace(";", ",").split(",") if t.strip()}
                        if a == b:
                            field_survived[f] += 1
                    elif f == "SuspicionLevel":
                        if str(mv).lower() == str(nv).lower():
                            field_survived[f] += 1
                    elif str(mv) == str(nv):
                        field_survived[f] += 1

        # Restrict the native side to the fields the adapter is CAPABLE of
        # carrying. Without this the comparison measures field availability --
        # the adapter cannot represent DeviceName, CountryCode and friends at
        # all -- rather than the fidelity of the transformation, which is the
        # question. What the adapter structurally cannot carry is a documented
        # limitation below, not a transfer error.
        native_matched = {f: native.get(f) for f in ADAPTER_FIELDS
                          if native.get(f) is not None
                          and str(native.get(f)).lower() != "nan"}

        v_native, m_native, e_native = verdict_for(native_matched, model, encoders)
        v_wazuh, m_wazuh, e_wazuh = verdict_for(mapped, model, encoders)
        native_errors += bool(e_native)
        wazuh_errors += bool(e_wazuh)
        if v_wazuh is not None and not e_wazuh:
            pipeline_ok += 1
        if v_native is not None and v_wazuh is not None:
            n_compared += 1
            if v_native == v_wazuh:
                n_agree += 1
            if m_native is not None and m_wazuh is not None:
                margin_deltas.append(abs(m_native - m_wazuh))

    # Does the adapter's output vocabulary actually exist in the model's
    # encoders? A field can survive the round trip structurally and still be
    # discarded at encode time, which is invisible to a field-survival count.
    #
    # Two different questions, kept apart because conflating them would
    # overstate the result:
    #
    #   SuspicionLevel -- the adapter MANUFACTURES this value from rule.level,
    #     so 'low'/'medium'/'high' is what it emits no matter what the source
    #     alert said. This applies to the round trip measured above.
    #
    #   Category -- the adapter PASSES THROUGH Wazuh's rule.groups. In this
    #     round trip the groups were seeded from GUIDE categories, so they
    #     survive; a real Wazuh alert carries 'syslog'/'sshd'/etc. The values
    #     probed here are therefore illustrative of real Wazuh traffic, NOT of
    #     the round trip above.
    #
    vocab = {}
    for field, adapter_values, scope in (
        ("SuspicionLevel", ["low", "medium", "high"],
         "manufactured by the adapter; applies to the round trip measured here"),
        ("Category", ["authentication_failed", "syslog", "sshd"],
         "illustrative real Wazuh rule.groups; NOT what the round trip above "
         "carried, since those groups were seeded from GUIDE categories"),
    ):
        enc = encoders.get(field)
        known = [str(c) for c in enc.classes_] if enc is not None else []
        unknown = [v for v in adapter_values if v not in known]
        vocab[field] = {
            "scope": scope,
            "encoder_known_value_count": len(known),
            "encoder_known_values_sample": known[:12],
            "adapter_emits": adapter_values,
            "adapter_values_unknown_to_encoder": unknown,
            "all_adapter_values_unknown": len(unknown) == len(adapter_values),
        }

    agreement = clopper_pearson(n_agree, n_compared) if n_compared else None

    # Separately: what happens if the FULL GUIDE row is scored directly. On this
    # branch that raises, because fallback_classifier has no encoder for free-text
    # columns like DeviceName. Recorded rather than hidden -- it is the bug PR #50
    # fixes, and it is why the comparison above is run on matched fields.
    full_row_probe = None
    probe = df.iloc[0].to_dict(); probe.pop("IncidentGrade", None)
    _, _, probe_err = verdict_for(probe, model, encoders)
    full_row_probe = {
        "scored_without_error": probe_err is None,
        "error": probe_err,
        "note": "scoring a full synthetic GUIDE row directly fails on this branch: "
                "fallback_classifier raises on a string column with no saved "
                "encoder. PR #50 (issue #38) fixes exactly this. It does not "
                "affect the matched-field comparison above, which passes only "
                "adapter-capable fields.",
    }

    result = {
        "experiment": "M5.2 PART A -- Wazuh Tier-1 schema-transfer fidelity",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "n_generated": args.n,
        "seed": args.seed,
        "accuracy_comparison_not_reported": {
            "reason": "the synthetic generator's IncidentGrade is drawn "
                      "independently of every feature, so it carries no signal",
            "evidence": learnability,
            "consequence": "a transfer-accuracy 'retention' figure would compare "
                           "chance with chance and would pass the issue's >=85% "
                           "criterion while measuring nothing",
            "precedent": "experiments/results/archive/agent_metrics.json was "
                         "withdrawn from this project for exactly this reason",
        },
        "verdict_agreement_native_vs_roundtripped": agreement,
        "comparison_basis": "matched adapter-capable fields on both sides "
                            f"({', '.join(['AlertTitle','DetectorId','Category','MitreTechniques','SuspicionLevel','Hour','DayOfWeek'])}), "
                            "so the only difference is the round-trip itself",
        "full_guide_row_probe": full_row_probe,
        "rf_margin_abs_delta": {
            "mean": round(float(np.mean(margin_deltas)), 6) if margin_deltas else None,
            "p95": round(float(np.percentile(margin_deltas, 95)), 6) if margin_deltas else None,
            "n": len(margin_deltas),
        },
        "schema_guardrail_pass_rate": clopper_pearson(schema_pass, args.n),
        "pipeline_completion_rate": clopper_pearson(pipeline_ok, args.n),
        "errors": {"native_path": native_errors, "wazuh_path": wazuh_errors},
        "encoder_vocabulary_compatibility": vocab,
        "field_survival": {
            f: {"present_in_source": field_present[f],
                "survived_round_trip": field_survived[f],
                "rate": round(field_survived[f] / field_present[f], 4)
                        if field_present[f] else None}
            for f in ADAPTER_FIELDS
        },
        "tier": "Tier-1 (synthetic only)",
        "finding_suspicionlevel_vocabulary_mismatch": {
            "severity": "actionable defect in src/integrations/wazuh_adapter.py",
            "what": "_suspicion_level() buckets Wazuh rule.level into "
                    "'low'/'medium'/'high'. The deployed model's SuspicionLevel "
                    "encoder knows only ['Incriminated', 'Suspicious', 'nan'], so "
                    "all three adapter outputs encode to -1 (unknown).",
            "consequence": "every Wazuh-origin alert loses its SuspicionLevel "
                           "signal entirely -- not degraded, discarded. The field "
                           "appears populated end to end, which is why a "
                           "field-survival count alone would not catch it.",
            "scope_note": "This one is unconditional: the adapter manufactures "
                          "the value from rule.level, so it holds for real Wazuh "
                          "traffic and for this round trip alike. The Category "
                          "mismatch recorded alongside it is different in kind -- "
                          "that field is passed through, so it only bites on real "
                          "Wazuh rule.groups, not on the round trip measured here.",
            "verified_against_real_guide": "GUIDE_Test.csv SuspicionLevel values "
                                           "are 'Suspicious' and 'Incriminated'; "
                                           "this is not an artefact of the "
                                           "synthetic generator's vocabulary.",
            "fix": "map rule.level onto GUIDE's own vocabulary rather than a "
                   "low/medium/high scale the model was never trained on.",
        },
        "limitations": [
            "Tier-1 only. Every alert here is synthetic; the labels are random "
            "and are deliberately not used. This is a schema-transfer measurement, "
            "not an accuracy measurement.",
            "No real Wazuh production data, labelled or otherwise, was available. "
            "Tier-2 -- real Wazuh alerts with analyst verdicts -- remains future "
            "work and no number in this project stands in for it.",
            "Rule-ID semantic alignment was not attempted. The adapter maps Wazuh "
            "rule.id into both AlertTitle and DetectorId because Wazuh does not "
            "separate them, so a Wazuh rule id and a GUIDE alert-title id that "
            "happen to share a value denote unrelated things. Verdict agreement "
            "below measures whether the classifier sees the same features, not "
            "whether those features mean the same thing in both domains.",
            "LastVerdict has no Wazuh equivalent and is dropped by design; it is "
            "excluded from the field-survival table rather than scored as a loss.",
        ],
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    print(f"\n  verdict agreement : {agreement['point']:.4f} "
          f"[{agreement['ci_lower']}, {agreement['ci_upper']}]  (n={agreement['n']})")
    print(f"  schema pass rate  : {result['schema_guardrail_pass_rate']['point']:.4f}")
    print(f"  pipeline completes: {result['pipeline_completion_rate']['point']:.4f}")
    print(f"  |margin| delta    : mean {result['rf_margin_abs_delta']['mean']}, "
          f"p95 {result['rf_margin_abs_delta']['p95']}")
    print("\n  encoder-vocabulary compatibility:")
    for f, v in vocab.items():
        flag = "  <- ALL UNKNOWN" if v["all_adapter_values_unknown"] else ""
        print(f"    {f:18} unknown to encoder: {v['adapter_values_unknown_to_encoder']}{flag}")
        print(f"    {'':18}   scope: {v['scope']}")
    print("\n  field survival across the round trip:")
    for f, v in result["field_survival"].items():
        print(f"    {f:18} {v['survived_round_trip']:>6}/{v['present_in_source']:<6} "
              f"{'' if v['rate'] is None else format(v['rate'], '.4f')}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
